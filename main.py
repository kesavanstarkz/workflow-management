import os
import base64
from flask import Flask, send_file, render_template, request, jsonify
from werkzeug.utils import secure_filename
from openai import OpenAI
import requests
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from PIL import Image
import io
from twilio.rest import Client
import urllib.request
from urllib.parse import urljoin

app = Flask(__name__)

# File upload configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'jfif', 'bmp', 'tiff'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------
# TWILIO CONFIG
# ---------------------------
TWILIO_ACCOUNT_SID = "AC4eee6488949447c317b15bfc7a878615"
TWILIO_AUTH_TOKEN = "7207eac60ffbcfb9286a36db1f5817a8"
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"  # Twilio WhatsApp number

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ---------------------------
# AZURE OPENAI CONFIG
# ---------------------------
azure_endpoint = "https://ai-foundary-rag.openai.azure.com/openai/v1"
azure_deployment = "gpt-4o"
azure_api_key = "DhoAt9lA57PwGhQykkSEL62W7KoXEpO48AnhFYQK3aYyhXtmJlxKJQQJ99BLAC77bzfXJ3w3AAAAACOG5pmr"

azure_client = OpenAI(
    base_url=azure_endpoint,
    api_key=azure_api_key
)

# OCR Config
OCR_API_KEY = "K81751319888957"
OCR_URL = "https://api.ocr.space/parse/image"

# Google Sheets Config
SPREADSHEET_ID = "1oQq7m0qMQadxeDZBGER4WXUvI7iwk2yM-yzKCi82pS4"
RANGE_NAME = "Sheet1!A1"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_to_jpeg(image_path):
    """Convert image to JPEG format if it's in a different format"""
    try:
        # Open the image
        img = Image.open(image_path)
        
        # Convert RGBA to RGB (for formats with transparency)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create a white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Create JPEG path
        base_path = os.path.splitext(image_path)[0]
        jpeg_path = base_path + '_converted.jpeg'
        
        # Save as JPEG
        img.save(jpeg_path, 'JPEG', quality=95)
        
        # Remove original if it was a different format
        if not image_path.lower().endswith('.jpeg') and not image_path.lower().endswith('.jpg'):
            try:
                os.remove(image_path)
            except:
                pass
        
        return jpeg_path
    except Exception as e:
        # If conversion fails, return original path
        print(f"Conversion error: {e}")
        return image_path

def encode_image(image_path):
    """Encode image to base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def process_image_with_azure(image_path):
    """Process image with Azure GPT-4o Vision - Extract username and streak"""
    try:
        image_base64 = encode_image(image_path)
        response = azure_client.chat.completions.create(
            model=azure_deployment,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract the username and streak number from this image. Return the response in this exact JSON format: {\"username\": \"<username>\", \"streak\": \"<number> days completed\"}. If you cannot find either value, use 'Unknown' or '0 days completed' respectively. Return ONLY the JSON, nothing else."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
        )
        result = response.choices[0].message.content.strip()
        return result
    except Exception as e:
        return f'{{"username": "Error", "streak": "Error: {str(e)}"}}'

def process_image_with_ocr(image_path):
    """Process image with OCR Space API"""
    try:
        with open(image_path, 'rb') as img:
            response = requests.post(
                OCR_URL,
                files={"filename": img},
                data={"apikey": OCR_API_KEY, "language": "eng"}
            )
        result = response.json()["ParsedResults"][0]["ParsedText"]
        return result
    except Exception as e:
        return f"OCR processing error: {str(e)}"

def save_to_sheets(azure_data, ocr_data=None):
    """Save extracted data to Google Sheets with headers"""
    try:
        import json
        
        creds = Credentials.from_service_account_file("credientials/cred.json")
        service = build("sheets", "v4", credentials=creds)
        
        # Parse Azure JSON response
        try:
            azure_json = json.loads(azure_data)
            username = azure_json.get("username", "Unknown")
            streak = azure_json.get("streak", "Unknown")
        except:
            username = "Parse Error"
            streak = azure_data
        
        # First, check if headers exist
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE_NAME
            ).execute()
            existing_values = result.get('values', [])
        except:
            existing_values = []
        
        # If no data exists or first row doesn't have headers, create them
        if not existing_values or len(existing_values) == 0:
            # Create headers
            headers = ["Username", "Streak"]
            header_body = {"values": [headers]}
            
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE_NAME,
                valueInputOption="RAW",
                body=header_body
            ).execute()
            
            # Now append the data
            row = [username, streak]
            
            values = [row]
            data_body = {"values": values}
            
            result = service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range="Sheet1!A2",  # Start from row 2 (after headers)
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=data_body
            ).execute()
        else:
            # Headers exist, just append data
            row = [username, streak]
            
            values = [row]
            data_body = {"values": values}
            
            result = service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE_NAME,
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=data_body
            ).execute()
        
        return True, f"{result.get('updates').get('updatedRows')} rows updated"
    except Exception as e:
        return False, f"Sheets error: {str(e)}"

def download_twilio_media(media_url):
    """Download image from Twilio URL"""
    try:
        auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        response = requests.get(media_url, auth=auth)
        
        if response.status_code == 200:
            # Get file extension from content-type
            content_type = response.headers.get('content-type', 'image/jpeg')
            extension = content_type.split('/')[-1]
            if extension == 'plain':
                extension = 'jpeg'
            
            # Save image
            filename = f"whatsapp_{int(__import__('time').time())}.{extension}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return filepath
        else:
            return None
    except Exception as e:
        print(f"Error downloading media: {e}")
        return None

@app.route("/whatsapp/webhook", methods=['POST'])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages"""
    try:
        from twilio.twiml.messaging_response import MessagingResponse
        
        # Get incoming message data
        incoming_msg = request.values.get('Body', '')
        sender = request.values.get('From', '')
        num_media = int(request.values.get('NumMedia', 0))
        
        response = MessagingResponse()
        
        # Check if message has media
        if num_media > 0:
            media_url = request.values.get('MediaUrl0', '')
            media_type = request.values.get('MediaContentType0', '')
            
            # Process only images
            if 'image' in media_type:
                # Download image
                filepath = download_twilio_media(media_url)
                
                if filepath:
                    # Convert to JPEG
                    filepath = convert_to_jpeg(filepath)
                    
                    # Process with Azure
                    azure_result = process_image_with_azure(filepath)
                    
                    # Process with OCR
                    ocr_result = process_image_with_ocr(filepath)
                    
                    # Save to Google Sheets
                    sheets_success, sheets_msg = save_to_sheets(azure_result, ocr_result)
                    
                    # Send response
                    import json
                    try:
                        azure_json = json.loads(azure_result)
                        username = azure_json.get("username", "Unknown")
                        streak = azure_json.get("streak", "Unknown")
                        
                        msg_text = f"✅ Data processed!\n\n📱 Username: {username}\n🔥 Streak: {streak}\n\n✓ Saved to Google Sheets"
                    except:
                        msg_text = f"✅ Image processed and saved!\n\n{azure_result}"
                    
                    response.message(msg_text)
                else:
                    response.message("❌ Error downloading image. Please try again.")
            else:
                response.message("❌ Please send an image file.")
        else:
            response.message("📸 Send me an image to extract streak data!")
        
        return str(response)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/whatsapp/send", methods=['POST'])
def send_whatsapp():
    """Send message to WhatsApp (for testing)"""
    try:
        data = request.get_json()
        to_number = data.get('to', '').strip()
        message = data.get('message', 'Hello from Flask!')
        
        if not to_number.startswith('whatsapp:'):
            to_number = f'whatsapp:{to_number}'
        
        msg = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_number,
            body=message
        )
        
        return jsonify({'success': True, 'message_sid': msg.sid}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/upload", methods=['POST'])
def upload_file():
    """Handle image upload and process with Azure"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'File type not allowed'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Convert to JPEG if needed
        filepath = convert_to_jpeg(filepath)
        
        # Process with Azure
        azure_result = process_image_with_azure(filepath)
        
        # Process with OCR
        ocr_result = process_image_with_ocr(filepath)
        
        # Save to Google Sheets
        sheets_success, sheets_msg = save_to_sheets(azure_result, ocr_result)
        
        return jsonify({
            'success': True,
            'azure_result': azure_result,
            'ocr_result': ocr_result,
            'sheets_saved': sheets_success,
            'sheets_message': sheets_msg,
            'filename': filename
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/process-default", methods=['GET'])
def process_default():
    """Process the default image"""
    image_path = "image/with_streaks_cropped.jpg"
    
    if not os.path.exists(image_path):
        return jsonify({'error': 'Default image not found'}), 404
    
    # Process with Azure
    azure_result = process_image_with_azure(image_path)
    
    # Process with OCR
    ocr_result = process_image_with_ocr(image_path)
    
    # Save to Google Sheets
    sheets_success, sheets_msg = save_to_sheets(azure_result, ocr_result)
    
    return jsonify({
        'azure_result': azure_result,
        'ocr_result': ocr_result,
        'sheets_saved': sheets_success,
        'sheets_message': sheets_msg
    }), 200

if __name__ == '__main__':
    # Get port from environment variable (Render sets PORT)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)