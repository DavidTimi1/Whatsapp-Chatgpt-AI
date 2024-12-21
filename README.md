# WhatsApp Bot with Flask

This is a Flask-based application that uses the Meta WhatsApp API to interact with users on WhatsApp. It features advanced capabilities such as **image recognition**, **image generation**, and **voice transcription** (e.g., processing voice notes). The bot is powered by OpenAI's GPT-3.5 API for conversational AI and plans to add support for **Google's Gemini API** in future updates. 

The application also includes **API key rotation** and **API key-to-request traffic management** for handling multiple keys efficiently.

---

## Features

### Core Functionality
- **WhatsApp API Integration**: Utilizes Meta's WhatsApp API for direct interaction. A Meta developer account setup is required to use this app.
- **Image Recognition**: Processes and recognizes uploaded images.
- **Image Generation**: Supports AI-generated images.
- **Voice Transcription**: Converts voice notes sent on WhatsApp into text for further processing.
- **AI-Powered Conversations**: Uses OpenAI's GPT-3.5 for dynamic, intelligent responses. Planned support for Gemini API is underway.

### Advanced Features
- **API Key Rotation**: Ensures seamless operation by distributing requests across multiple API keys.
- **Traffic Management**: Balances traffic load across API keys for efficient utilization.

---

## Requirements

### Prerequisites
- **Meta Developer Setup**: You need to set up a Meta developer account and configure the WhatsApp Business API to obtain the required credentials.
- **OpenAI API Key**: A valid OpenAI API key to enable AI-powered conversational capabilities.
- **Python**: Version 3.8 or above.
- **Flask**: Installed as the core framework for this app.

---

## Installation

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/yourusername/whatsapp-bot-flask.git
   cd whatsapp-bot-flask
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set Up Environment Variables**: Create a `.env` file in the project root and configure the required environment variables (see below).

4. **Run the App**:
   ```bash
   flask run
   ```

---

## Environment Variables

To configure the application, the following environment variables must be set in a `.env` file:

### Meta WhatsApp API
- `WHATSAPP_API_BASE_URL`: The base URL for the WhatsApp Business API (e.g., `https://graph.facebook.com/v15.0`).
- `WHATSAPP_PHONE_NUMBER_ID`: The ID of your WhatsApp Business account's phone number.
- `WHATSAPP_ACCESS_TOKEN`: Your Meta API access token for authenticating requests.

### OpenAI API
- `OPENAI_API_KEYS`: A comma-separated list of OpenAI API keys for key rotation (e.g., `key1,key2,key3`).
  
- Voice Transcription (Using **OpenAi's WHISPER** (No additional key required)
  
- Image Recognition and Generation (Using **OpenAi's DALLE** (No additional key required)
  

### Server Configuration
- `FLASK_ENV`: Set to `development` for development mode or `production` for production.
- `PORT`: Port on which the app will run (default is `5000`).

---

## Usage

### WhatsApp API Setup
1. Complete the Meta developer setup as described in the [Meta WhatsApp API Documentation](https://developers.facebook.com/docs/whatsapp).
2. Configure the webhook URL in your Meta dashboard to point to your app's endpoint (e.g., `https://yourdomain.com/webhook`).

### API Key Management
The app supports **multi-key management** for OpenAI or other third-party APIs. Keys will automatically rotate based on usage limits to ensure uninterrupted service.

### Endpoints
- **Webhook Endpoint**: Handles incoming messages from WhatsApp.
- **Image Uploads**: Processes images sent by users.
- **Voice Notes**: Converts voice notes into text and generates responses.

---

## Planned Features
- Support for **Gemini API** for enhanced conversational AI.
- Improved traffic analytics for API key rotation.
- Enhanced monitoring and alerting for key usage limits.
- Scheduled messaging *(tried this initially but failed due to HTTP request-response nature)*


---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Contributing

We welcome contributions! Feel free to open an issue or submit a pull request.

---

## References

- [Meta WhatsApp API Documentation](https://developers.facebook.com/docs/whatsapp)
- [OpenAI API Documentation](https://platform.openai.com/docs/)
