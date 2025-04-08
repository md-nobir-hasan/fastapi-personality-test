from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware  # Import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
from haystack import Pipeline
from haystack.components.preprocessors import DocumentSplitter
from haystack.components.builders.prompt_builder import PromptBuilder
from haystack.utils import Secret
from haystack.components.generators import OpenAIGenerator
from haystack import Document
import os 
from dotenv import load_dotenv 
import json
import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import threading

#env file load
load_dotenv()
openai_api_key = os.getenv('OPENAI_API_KEY')
openai_api_key = Secret.from_token(openai_api_key)

#Pattern of a question
class SingleQuestion(BaseModel):
    text: str 
    answer: str
    trait: Literal["E", "I", "S", "N", "T", "F", "J", "P"]
class requestData(BaseModel):
    name: str
    email: str
    phone: str
    questions: List[SingleQuestion]

class qoaResponse(BaseModel):
    total_question: int
    correct_anaswer: int
    wrong_answer: int
    results: list

# Function to generate documents from user responses
def llm_pipeline(api_key):
    """
    This function creates an LLM-powered pipeline to determine someone's MBTI type.

    Parameters
    ----------
    api_key : str
        OpenAI API key

    Returns
    -------
    pipeline : Pipeline (Haystack)
        A pipeline that can be used to determine someone's MBTI type.
    """
    prompt_template = """
    Bestem en persons personlighedstype ved hjælp af Myers-Briggs Type Indicator (MBTI)-testen. I denne test
    svarer brugeren på en række spørgsmål ved at vælge "Enig" eller "Uenig". Spørgsmålene er
    mærket efter egenskaber, hvor egenskaberne er:
    E = Extraversion
    I = Introversion
    S = Sensing
    N = Intuition
    T = Thinking
    F = Feeling
    J = Judging
    P = Perceiving

    Giv en title på personlighedstypen baseret på MBTI og hvilken rolle de passer til.
    I din beskrivelse nævn de definerende karakteristika for personlighedstypen med max 100 ord.
    Giv også en procentfordeling af personlighedstræk, som sætter dem i kasser for [Extraversion og Introversion], [Sensing og Intuition], [Thinking og Feeling], og [Judging og Perceiving]. Linjeskift for hver personligheidstræk.
    Til sidst skal du sætte i punkter hvilke 4 styrker og 4 svagheder personlighedstypen har.

    **Return the response in the following JSON format with English keys and Danish values:**
    {
        "mbti_type": "[MBTI type på dansk]",
        "title": "[Kaldenavn for denne personlighedstype på dansk]",
        "tagline": "[En kort sætning der beskriver essensen af denne personlighedstype]",
        "summary": "Ifølge FlexTemps personlighedstest, er du: [MBTI type]",
        "description": "[Beskrivelse af personlighedstypen]",
        "percentage_distribution": {
            "Extraversion": X,
            "Introversion": Y,
            "Sensing": X,
            "Intuition": Y,
            "Thinking": X,
            "Feeling": Y,
            "Judging": X,
            "Perceiving": Y
        },
        "strengths": ["[Stærke egenskaber 1]", "[Stærke egenskaber 2]", "[Stærke egenskaber 3]", "[Stærke egenskaber 4]"],
        "weaknesses": ["[Svage egenskaber 1]", "[Svage egenskaber 2]", "[Svage egenskaber 3]", "[Svage egenskaber 4]"]
    }

    Context:
    {% for doc in documents %}
        Question: {{ doc.content }} Response: {{ doc.meta['answer'] }} Personality trait: {{doc.meta['trait']}} \n
    {% endfor %};
    Question: {{query}}
    \n
    """
    splitter = DocumentSplitter(split_length=100, split_overlap=5)
    prompt_builder = PromptBuilder(prompt_template)
    llm = OpenAIGenerator(api_key=openai_api_key, 
                          model='gpt-4o',
                          generation_kwargs={"temperature":0.1})

    pipeline = Pipeline()
    pipeline.add_component("splitter", splitter)
    pipeline.add_component(name="prompt_builder", instance=prompt_builder)
    pipeline.add_component(name="llm", instance=llm)
    pipeline.connect("splitter.documents", "prompt_builder.documents")
    pipeline.connect("prompt_builder", "llm")

    return pipeline

# Modified ResultsComponent to display MBTI type and description
def generate_documents_from_responses(questions):
    """
    This function takes responses and generates Haystack Documents.

    Parameters
    ----------
    responses : list
        A list of responses to the MBTI questions. Each response is of type dict
        and has the following keys: 'text' (str), 'trait' (str), 'answer' (str).

    Returns
    -------
    documents : list
        A list of Haystack Documents.
    """
    documents = []
    for question in questions:
        nmeta = {
            'trait': question.trait,
            'answer': question.answer
        }
        documents.append(Document(content=question.text, meta=nmeta))

    return documents

# Define FastAPI app
app = FastAPI()


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (you can specify specific domains instead of "*")
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Mount other static files (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html at "/"
@app.get("/")
async def read_index():
    return FileResponse("static/index.html")




@app.post('/result',status_code=200)
def qoa(request:requestData):
    questions = request.questions
    pipeline = llm_pipeline(openai_api_key)
    documents = generate_documents_from_responses(questions)
    query = "Baseret på svarene, hvad er denne brugers Myers-Briggs personlighedstype?"
    answer = pipeline.run(data={'splitter': {'documents': documents}, "prompt_builder": {"query": query}})
    mbti_type_llm = answer['llm']['replies'][0]
    
    # Step 1: Remove the markdown code block
    cleaned_response = mbti_type_llm.strip().replace("```json\n", "").replace("```", "")
    
    # Step 2: Parse the JSON string into a Python dictionary
    response_json = json.loads(cleaned_response)
    
    # No need to split the title anymore as the format has been updated in the prompt
    # The LLM will now provide separate title and nickname fields
    
    # Save questions and response to a text file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"mbti_result_{timestamp}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("MBTI Test Results\n")
        f.write("=================\n\n")

        f.write("\nPersonal Details:\n")
        f.write(f"Name: {request.name}\n")
        f.write(f"Email: {request.email}\n")
        f.write(f"Phone: {request.phone}\n\n")

        f.write("\nQuestions and Answers:\n")
        for i, question in enumerate(questions, 1):
            f.write(f"{i}. Question: {question.text}\n")
            f.write(f"   Answer: {question.answer}\n")
            f.write(f"   Trait: {question.trait}\n\n")
        
        f.write("\nMBTI Results:\n")
        f.write(f"MBTI Type: {response_json['mbti_type']}\n")
        f.write(f"Title: {response_json['title']}\n")
        f.write(f"Tagline: {response_json['tagline']}\n")
        f.write(f"Summary: {response_json['summary']}\n")
        f.write(f"Description: {response_json['description']}\n\n")
        
        f.write("Percentage Distribution:\n")
        for trait, percentage in response_json['percentage_distribution'].items():
            f.write(f"{trait}: {percentage}%\n")
        
        f.write("\nStrengths:\n")
        for strength in response_json['strengths']:
            f.write(f"- {strength}\n")
        
        f.write("\nWeaknesses:\n")
        for weakness in response_json['weaknesses']:
            f.write(f"- {weakness}\n")
    
    # Start a background thread to upload the file to Google Drive
    # This way the API can return immediately without waiting for the upload
    threading.Thread(target=upload_to_drive, args=(filename,), daemon=True).start()
    
    # Return the updated JSON response immediately
    return response_json

def upload_to_drive(filename):
    """
    Upload a file to Google Drive in a background thread
    
    Parameters:
    filename (str): The name of the file to upload
    """
    try:
        # Path to your service account key file
        service_account_file = 'arched-pier-454009-r8-82a8a7a8cd08.json'
        
        # Define the scopes
        SCOPES = ['https://www.googleapis.com/auth/drive']
        
        # Authenticate and create the Drive service
        credentials = Credentials.from_service_account_file(
            service_account_file, scopes=SCOPES)
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Get or create the "personality-test" folder
        folder_name = "personality-test"
        folder_id = get_or_create_folder(drive_service, folder_name)
        
        # Define file metadata with the folder ID
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        
        # Create a media object for the file
        media = MediaFileUpload(filename, mimetype='text/plain')
        
        # Upload the file
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        print(f'File successfully uploaded to Google Drive folder "{folder_name}". File ID: {file.get("id")}')
    except Exception as e:
        print(f"Error uploading file to Google Drive: {e}")

def get_or_create_folder(drive_service, folder_name):
    """
    Get or create a folder in Google Drive
    
    Parameters:
    drive_service: The Google Drive service instance
    folder_name (str): The name of the folder to find or create
    
    Returns:
    str: The ID of the folder
    """
    # Check if folder already exists
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    folders = results.get('files', [])
    
    # If folder exists, return its ID
    if folders:
        print(f'Found existing folder "{folder_name}" with ID: {folders[0]["id"]}')
        return folders[0]['id']
    
    # If folder doesn't exist, create it
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    
    folder = drive_service.files().create(
        body=folder_metadata,
        fields='id'
    ).execute()
    
    folder_id = folder.get('id')
    print(f'Created new folder "{folder_name}" with ID: {folder_id}')
    return folder_id

@app.get('/test-drive-upload', status_code=200)
def test_drive_upload():
    """
    Test endpoint to verify Google Drive upload functionality
    Creates a simple test file and uploads it to Google Drive
    """
    # Create a simple test file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"test_file_{timestamp}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("This is a test file to verify Google Drive upload functionality.\n")
        f.write(f"Created at: {datetime.datetime.now().isoformat()}\n")
    
    try:
        # Upload the file synchronously for testing purposes
        upload_result = upload_to_drive_sync(filename)
        return {
            "status": "success",
            "message": "Test file created and upload attempted",
            "filename": filename,
            "upload_result": upload_result
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error during upload: {str(e)}",
            "filename": filename
        }

def upload_to_drive_sync(filename):
    """
    Upload a file to Google Drive synchronously (for testing)
    
    Parameters:
    filename (str): The name of the file to upload
    
    Returns:
    dict: Information about the upload result
    """
    try:
        # Try multiple possible locations for the service account file
        service_account_file = None
        possible_locations = [
            'arched-pier-454009-r8-82a8a7a8cd08.json',  # Current directory
            '/etc/secrets/arched-pier-454009-r8-82a8a7a8cd08.json',  # Secret files location
            os.path.join(os.path.dirname(__file__), 'arched-pier-454009-r8-82a8a7a8cd08.json')  # App root
        ]
        
        for location in possible_locations:
            if os.path.exists(location):
                service_account_file = location
                print(f"Found service account file at: {location}")
                break
                
        if not service_account_file:
            raise FileNotFoundError("Could not find service account JSON file in any of the expected locations")
        
        # Define the scopes
        SCOPES = ['https://www.googleapis.com/auth/drive']
        
        # Authenticate and create the Drive service
        credentials = Credentials.from_service_account_file(
            service_account_file, scopes=SCOPES)
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Get or create the "personality-test" folder
        folder_name = "personality-test"
        folder_id = get_or_create_folder(drive_service, folder_name)
        
        # Define file metadata with the folder ID
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        
        # Create a media object for the file
        media = MediaFileUpload(filename, mimetype='text/plain')
        
        # Upload the file
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        file_id = file.get('id')
        print(f'File successfully uploaded to Google Drive folder "{folder_name}". File ID: {file_id}')
        
        return {
            "success": True,
            "file_id": file_id,
            "folder_name": folder_name,
            "folder_id": folder_id
        }
    except Exception as e:
        print(f"Error uploading file to Google Drive: {e}")
        raise e  # Re-raise the exception to be caught by the test endpoint

    #response from openai
