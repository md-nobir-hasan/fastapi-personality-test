from fastapi import FastAPI 
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

#env file load
load_dotenv()
openai_api_key = os.getenv('OPENAI_API_KEY')
openai_api_key = Secret.from_token(openai_api_key)

#Pattern of a question
class SingleQuestion(BaseModel):
    text: str 
    answer: str
    trait: Literal["E", "I", "S", "N", "T", "F", "J", "P"]

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
    I din beskrivelse nævn de definerende karakteristika for personlighedstypen med max 100 ord
    Giv også en procentfordeling af personlighedstræk, som sætter dem i kasser for [Extraversion og Introversion], [Sensing og Intuition], [Thinking og Feeling], og [Judging og Perceiving]. Linjeskift for hver personlighedstræk.
    Til sidst skal du sætte i punkter hvilke 4 styrker og 4 svagheder personlighedstypen har.
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


app = FastAPI()
@app.get('/', status_code=200)
def index():
    return "Welcome to Personality test API"

@app.post('/result',status_code=200)
def qoa(questions:List[SingleQuestion]):
    total_question = len(questions)
    
    #mbti_type_classic = classic_mbti_weighted(responses)
    pipeline = llm_pipeline(openai_api_key)
    # return {'linke':119,'total_question':total_question, 'api_key':api_key}
    documents = generate_documents_from_responses(questions)
    query = "Baseret på svarene, hvad er denne brugers Myers-Briggs personlighedstype?"
    answer = pipeline.run(data={'splitter': {'documents': documents}, "prompt_builder": {"query": query}})
    mbti_type_llm = answer['llm']['replies'][0]
    return mbti_type_llm

    #response from openai
