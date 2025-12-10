def save_to_sheets(azure_data, ocr_data=None):
    try:
        import json

        # CLEAN JSON
        azure_data = azure_data.strip()
        azure_data = azure_data.replace("```json", "").replace("```", "")

        # SHEET CREDENTIALS
        creds = Credentials.from_service_account_file("credentials/cred.json")
        service = build("sheets", "v4", credentials=creds)

        # Parse JSON correctly
        try:
            azure_json = json.loads(azure_data)
            username = azure_json.get("username", "Unknown")
            streak = azure_json.get("streak", "Unknown")
        except:
            print("❌ JSON PARSE ERROR:", azure_data)
            username = "Parse Error"
            streak = azure_data

        # Append row
        row = [username, streak]

        body = {"values": [row]}

        result = service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="Sheet1!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()

        print("Sheets Update:", result)
        return True, "Row added successfully."

    except Exception as e:
        print("🔥 GOOGLE SHEETS ERROR:", str(e))
        return False, f"Sheets error: {str(e)}"
