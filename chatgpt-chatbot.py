import openai
import os
import re
import requests
import threading
import time
import hmac
import hashlib
import mimetypes
import tiktoken

from datetime import datetime as dt, timedelta as td
from dotenv import dotenv_values
from flask import Flask, request
from json import loads as load_json, dumps as dump_json
from tempfile import mkstemp
from time import sleep

# Configure application
app = Flask(__name__)


# Load enviromental variables containing keys and secrets
key_config = dotenv_values("env.env")
WABA_ID = key_config["waba_ib"] # Whatsapp Business Account ID
WABA_PHONE = key_config["waba_phone"] # Phone associated with WABA
WABA_PHONE_ID = key_config["waba_phone_id"] # Phone id for WABA
META_TOKEN = key_config["meta_access_token"] # Access token for meta app
META_APP_SECRET = key_config["meta_app_secret"] # App secret
META_API = key_config["meta_api_version"] # Api Version

# if using multiple keys
openai_api_keys = load_json(key_config["openai"])
# if using a single key
openai_api_keys = [key_config["openai"]]



class AI_API:
    def __init__(self, openai_api_keys, limit=3):
        self._limit_per = limit
        self._limit = limit * len(openai_api_keys)
        self._current = 0
        self._keys = openai_api_keys
        self.lock = threading.Lock()
        self.counter = []
        self.starttime = []
        self.t = []

        for t in range(len(self._keys)):
            # resets every minute
            self.t.append(threading.Timer(60, self.reset, [t]))
            self.counter.append(0)
            self.starttime.append(None)
    
    def reset(self, index):
        with self.lock:
            # reset the value to zero and add a new timeout
            self.counter[index] = 0
            self.t[index] = threading.Timer(60, self.reset, [index])
            self.starttime[index] = None
    
    def get_key(self, purpose="chat"):
        with self.lock:
            if purpose != "chat":
                return self._keys[self._current]
            
            # if the current one is full use the next
            if self.counter[self._current] == self._limit_per:
                self._current = (self._current + 1) % len(self._keys)
            
            # if the next is not full use
            if self.counter[self._current] < self._limit_per:
                if not self.counter[self._current]:
                    # activate timeout till reset
                    self.t[self._current].start()

                self.counter[self._current] += 1
                self.starttime[self._current] = int(time.time())
                return self._keys[self._current]
            else:
                raise Exception(f"Wait {self.get_time_left()} sceonds till next prompt")
    
    def get_time_left(self):
        return 60 - (int(time.time()) - self.starttime[self._current])


# NOT WORKING IDK WHY
# ENDS UP NOT SENDING AT THE RIGHT TIME UNTIL A FOLLOW UP MESSAGE IS SENT
# IT THEN SENDS BOTH THE PREVIOUS AND NEW MESSAGES FROM A 'SECURE SERVICE FROM META'

class Schedule_Message:
    def __init__(self, message, to, mess_type, details, timestring, reference):
        self.delay = self.get_delay(timestring)
        self.receiver = to
        self.ref = reference
        self.ai_res = message.upper() if mess_type == "text" else chat_ai(message,to,mess_type,details)
        # self.timeout = threading.Timer(self.delay, send_whats_message, [self.ai_res, self.ref])
        self.timeout = threading.Thread(target=self.wait_for_time)
        self.timeout.start()
        print(f"Message due in {self.delay} seconds")

    def get_delay(self, string):
        parts = string.split(":") if ":" in string else string.split(" ")
        if 'minute' in parts[1]:
            return int(parts[0]) * 60
        return (dt.now() - get_next_time(string)).seconds

    def wait_for_time(self):
        sleep(self.delay)
        send_whats_message(self.ai_res, self.receiver, self.ref)


openai_api = AI_API(openai_api_keys)

TOKEN_ENCODER = tiktoken.encoding_for_model("gpt-3.5-turbo") # Uses gpt-3.5 turbo
MAX_TOKENS = 3800
total_tokens = 0

# # Function to calculate token count in a text
token_count = lambda text: len(TOKEN_ENCODER.encode(text))



def verify_webhook(data, hmac_header):
    app_secret = key_config["app_secret"]
    hmac_recieved = str(hmac_header).removeprefix('sha256=')
    digest = hmac.new(app_secret.encode('utf-8'), data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(hmac_recieved, digest)


@app.route("/webhooks", methods=["POST","GET"])
def webhook():
    if request.method == "GET":
        # # to log meta endpoint verification json payload (unnecessary)
        #     with open("webhook log.txt", 'x') as hooklog:
        #         det = f"[{int(time.time())}] - GET: {request.args}\n"
        #         hooklog.write(det)
        return request.args.get("hub.challenge")

    # IF A POST REQUEST WAS MADE
    
    # verify that the source of the webhook is actually whatsapp
    authentic = verify_webhook(request.get_data() ,request.headers.get('X-Hub-Signature-256'))
    
    if not authentic:
        # to log fake json payload
        with open("webhook log.txt", 'a') as hooklog:
            det = f"[Fake - {int(time.time())}] - POST: {dump_json(json,indent=2)}\n"
            hooklog.write(det)
        return "Forbidden", 403
    
    json = request.get_json()
    
    # load contacts list from storage
    with open("ai_contacts.json", "r") as contacts_file:
        ai_contacts_json = contacts_file.read()
    ai_contacts = load_json(ai_contacts_json)
    
    changes = json["entry"][0]["changes"][0]["value"]
    
    if json["entry"][0]["id"] == WABA_ID and changes.get("contacts") and changes.get("messages"):
        # initialize the message and contacts dictionary
        msg_obj = changes["messages"][0]
        contact_obj = changes["contacts"][0]
    
        # mark message as read
        headers = {'Authorization': f'Bearer {META_TOKEN}','Content-Type': 'application/json'}
        data = dump_json({
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": msg_obj["id"]
        })
        response = requests.post(f'https://graph.facebook.com/{META_API}/{WABA_PHONE_ID}/messages', headers=headers, data=data)
        print("Message has been read!" if response.status_code == 200 else f"Failed: {response.json()}")
        
        # process request if sender is in contact list
        if contact_obj["wa_id"] in ai_contacts:
            try:
                mess = reaction = ai_response = None
                
                # check which type of message was sent (only text / audio support)
                if msg_obj.get("type") == "text":
                    mess = msg_obj["text"]["body"]
                elif msg_obj.get("type") == "audio":
                    mess = transcribe_audio(msg_obj["audio"]["id"])
                else: mess = ""
                
                # test message for presence f regular expressions
                regex_res = regex_check(mess)

                if regex_res and not regex_res[0]: # prevent handling of scheduled message
                    # if the message is to be scheduled
                    scheduled = regex_res[0]
                    if scheduled:
                    # ... Not working ...
                        tmp = regex_res[1]
                        Schedule_Message(tmp["message"], contact_obj["wa_id"], tmp["type"], tmp, tmp["time"], msg_obj["id"])
                        reaction = '👍'
                    else:
                        # if the test returned a request for an image file
                        ai_response = chat_ai(user=contact_obj["wa_id"],type=regex_res[1]["type"],details=regex_res[1])
                else:
                    # if the regex test failed
                    ai_response = chat_ai(mess,contact_obj["wa_id"])
            
            except Exception as err:
                ai_response = f"error: {err}"
            
            finally:
                # send final result
                send_whats_message(ai_response, contact_obj["wa_id"], msg_obj["id"], reaction)
    else:
        # if the sender is not in contact list, log message
        with open("webhook log.txt", 'a') as hooklog:
            det = f"Unregistered - [{int(time.time())}] - POST: {dump_json(json, indent=4)}\n"
            hooklog.write(det)
    
    # In all cases return OK
    return {"success": "Webhook event received"}, 200


def send_whats_message(message, to, reply_id, reaction=None):
    # set request headers
    headers = {'Authorization': f'Bearer {META_TOKEN}', 'Content-Type': 'application/json'}

    # wireframe of request body
    data_proto = {
        "messaging_product": "whatsapp",
        "to": to,
        "context": {"message_id": reply_id}
    }

    # to send a reaction
    if reaction:
        data_proto["type"] = "reaction"
        data_proto["reaction"] = {"message_id":reply_id, "emoji":reaction}

    # to send multiple images
    elif isinstance(message, list):
        for img_link in message:
            data_proto["type"] = "image"
            data_proto["image"] = {"link": img_link}

    # to send text
    else:
        # send the result
        data_proto["type"] = "text"
        data_proto["text"] = {"preview_url": True,"body": message}

    data = dump_json(data_proto)
    response = requests.post(f'https://graph.facebook.com/{META_API}/{WABA_PHONE_ID}/messages', headers=headers, data=data)
    print("Successfully sent message" if response.status_code == 200 else f"Failed to send message: {response.json()}")


# returns text from uploaded audio file
def transcribe_audio(file_id):
    # get a url to download the file from meta
    headers = {'Authorization': f'Bearer {META_TOKEN}','Content-Type': 'application/json'}
    response = requests.get(f'https://graph.facebook.com/{META_API}/{file_id}', headers=headers)

    if response.status_code != 200: print (f"Failed to get file url: {response.json()}")
    else:
        # fetch the file
        res = response.json()
        mime = res["mime_type"]

        response = requests.get(res["url"], headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to download file: {response.json()}")

        # check for file type support
        supported_audio_ext = [".mp3" , ".mp4" , ".mpeg" , ".mpga" , ".m4a" , ".wav" , ".webm"]
        ext = mimetypes.guess_extension(mime)
        if not ext in supported_audio_ext: raise Exception("Unsupported file type")

        # create tmp file
        tmp_file = mkstemp(ext)

        # write and read data to and from file 
        with open(tmp_file[1], "wb") as metafile:
            metafile.write(response.content)
        with open(tmp_file[1], "rb") as metafile:
            openai.api_key = openai_api.get_key("audio")
            transcript = openai.Audio.transcribe("whisper-1", metafile, language="en", prompt="Transcribe this file.")
        
        # delete tmp file
        os.remove(tmp_file[1])
        return transcript["text"]


# send message to openai apis
def chat_ai(message, user, type=None, details=None):
    if not message and not type:
        return "I'm sorry for any misunderstanding, but I don't have the capability to view or analyze images or other files. I am based on text or audio only and I don't have access to visual content. If you have any other questions or need information I will do my best to assist you."

    # Load previous conversations
    with open(f"{user}_whatsappAI.json", "r") as ai_history:
        saved_hist = ai_history.read()
    conversations = load_json(saved_hist)

    final_ai_res = assistant_reply = role = None

    new_convo = {"role": "user", "content": message}
    # Calculate tokens used for the new user message
    conversations.append(new_convo)
    # Calculate total tokens used in the conversation
    total_tokens = conversation_tokens(conversations)

    if total_tokens > MAX_TOKENS:
        print(f"... Adjusting Token ...  Currently at {total_tokens}")
        token_management_acad(conversations)

    try:
        # get response from img gen api
        if type == "image":
            openai.api_key = openai_api.get_key("image")
            img_res = openai.Image.create(
                prompt=details['descr'],
                n=details['n'],
                size="256x256" # [256, 512, 1024]
            )

            assistant_reply = f"Here {'is an image link' if details['n'] == 1 else 'are image links'} relating to {details['descr'].upper()} you asked for: "
            conversations.append({"role": "assistant", "content": assistant_reply})
            save_ai_history(conversations, user)

            final_ai_res = []
            for index, value in enumerate(img_res['data']):
                final_ai_res.append(value["url"])

        else:
            # using gpt-3.5 turbo

            # requests a key and keeps track
            openai.api_key = openai_api.get_key()

            # Send the conversation to OpenAI API
            request = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages= conversations,
                max_tokens = 256
            )

            response = request.choices[0]["message"]
            assistant_reply = response["content"]
            role = response["role"]
            case_res = assistant_reply.lower()

            # handle more cases of img gen not caught by regex but caught by gpt-3.5
            # if "image generation" in case_res:
            #     res = load_json(assistant_reply)
            #     img_res = openai.Image.create(
            #         prompt=res['translation'],
            #         n=res['n'],
            #         size="256x256"
            #     )

            # assistant_reply = f"Here {'is an image link' if res['n'] == 1 else 'are image links'} relating to {res['description'].upper()} you asked for: "
            # gen_images = []
            # for index, value in enumerate(img_res['data']):
                # gen_images.append(value["url"])
            # final_ai_res = gen_images

            # else:
                # # Extract the assistant's reply
                # final_ai_res = assistant_reply
            
    except Exception as err:
        final_ai_res = f"error: {err}"

    else:
        # add ai's reply and save history
        conversations.append({"role": role, "content": assistant_reply})
        save_ai_history(conversations, user)

    finally:
        # return the ai's reply
        return final_ai_res


# count number of tokens in entire conversation
def conversation_tokens(conversations):
    tokens = 0
    for convo in conversations:
        tokens += token_count(convo["content"])
    return tokens


# function to manage token overflow (exceeding max)
def token_management_acad(conversations):
    # crop messages
    broke = False
    length = len(conversations)
    tok = conversation_tokens(conversations)
    i = 0

    # not editing first and last 2 chats
    while i < length-4:
        j = i+2
        trunc_res = truncate_message(conversations[j]["content"])
        conversations[j]["content"] = trunc_res[0]
        tok -= trunc_res[1]
        i+=1
        if  tok < MAX_TOKENS:
            print("New total: ", tok)
            broke = True
            break

    if not broke:
        i = 0
        while i < length-4:
            j = i+2
            tok -= token_count(conversations[j]["content"])
            del conversations[j]
            i+=1
            if tok < MAX_TOKENS:
                print("New total: ", tok)
                break
    return tok


# Function to truncate long messages while preserving context
def truncate_message(message):
    msg_count = token_count(message)
    trunc = 0 # truncated tokens
    if msg_count > 100:
        elps = None # no ellipsis
        char_count = 300

        if len(message) > char_count + 20:
            elps = message[char_count : char_count + (20)].split(" ")[0] + "..." # just to make sure it ends after a word, not between
            message = message[:char_count] + elps

        trunc = msg_count - token_count(message)
    # returns the truncated text and the loss in tokens
    return message, trunc


# saves user history in file system
def save_ai_history(messages, user):
    with open(f"{user}_whatsappAI.json", "w") as out_json:
        out_json.write(dump_json(messages, indent=4))


# regex function to get user intent
def regex_check(phrase: str):
    # Message Schedule -NOT WORKING-
    # Pattern 1: 'schedule a message', 'of' or 'containing', 'for', number (integer), 'minutes'
    pattern1 = r'schedule (a message|[0-5] image*s?) (of|containing|about|on)\s(.*)\sfor\s(\d+:\d+)?(\d+ minute*s?)?'

    # Pattern 2: 'in', number (integer), 'minutes', 'send' or 'generate' or 'give me' or 'remind me to' or 'reply with', 'a message' or 'an image'
    pattern2 = r'((in|by) (\d+\s+minute*s?|\d+:\d+)\s)?(send me|generate|give me|reply with|remind me to)\s(a message|\d+\s+image*s?)?\s*((.*)\s(in|by)?\s(\d+\s+minute*s?|\d+:\d+)$|.*$)?'

    # Image gen
    # Pattern 3: 'generate' or 'give me' or 'send me' or 'reply with', 'a message' or '{an or number} images'
    pattern3 = r"(generate|give me|send me|reply with) (an|a|[0-5]) (image*s? of|showing|about|depicting)"

    search1 = re.match(pattern1, phrase, re.IGNORECASE)
    if search1:
        time = search1.group(5) if search1.group(5) else search1.group(4)
        type = search1.group(1)
        message = search1.group(3)
        if time and type and message:
            return True, {'time':time,'type':type,'message':message}|({'type':'image','n':int(type.split(" ")[0]),'descr':message} if 'image' in type else {})


    search2 = re.match(pattern2, phrase, re.IGNORECASE)
    if search2:
        time = search2.group(9) if search2.group(9) else search2.group(3)
        type = search2.group(5) if search2.group(5) else "text"
        message = search2.group(7) if search2.group(7) else search2.group(6)
        if time and type and message:
            return True, {'time':time,'type':type,'message':message}|({'type':'image','n':int(type.split(" ")[0]),'descr':message} if 'image' in type else {})


    search3 = re.match(pattern3, phrase, re.IGNORECASE)
    if search3:
        n = search3.group(2)
        number_requested = 1 if not n.isdigit() else int(n)
        item_requested = phrase[phrase.span()[1] :]
        return False, {"type": "image", "n": number_requested, "descr": item_requested}

    print("No pattern matched.") # can comment this sir
    return


# returns datetime till next occurence of time within 24hrs
def get_next_time(time_str):
    current_time = dt.now() # cuurent datetime
    target_time = dt.strptime(time_str, '%H:%M')

    if current_time.time() > target_time.time():
        next_time = dt.combine(current_time.date() + td(days=1), target_time.time())
    else:
        next_time = dt.combine(current_time.date(), target_time.time())

    return next_time
