from fastapi import FastAPI 
from pydantic import BaseModel
from typing import List, Optional
import openai
import os 
from dotenv import load_dotenv 

#env file load
load_dotenv()

#Pattern of a question
class SingleQuestion(BaseModel):
    question: str
    options: Optional[List[str]] = []
    answer: str

class qoaResponse(BaseModel):
    total_question: int
    correct_anaswer: int
    wrong_answer: int
    results: list

app = FastAPI()

@app.post('/',response_model=qoaResponse,status_code=200)
def qoa(questions:List[SingleQuestion]):

    total_question = len(questions)
    correct_answer = total_question - 1
    wrong_answer = correct_answer - 1
    return qoaResponse(total_question=total_question, correct_anaswer=correct_answer, wrong_answer=wrong_answer,results=questions)
    #response from openai
