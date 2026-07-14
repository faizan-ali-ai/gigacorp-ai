import os
import json
import shutil
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import chromadb
import google.generativeai as genai

from langchain_groq import ChatGroq
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings


load_dotenv()


app = FastAPI(
    title="GigaCorp Enterprise Support API Engine",
    version="6.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatQueryRequest(BaseModel):
    case_id: str
    message: str


class ConfigurationError(Exception):
    pass


DATA_DIR = Path("/tmp/gigacorp_data")

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)

MEMORY_FILE = Path("chat_memory.json")


def load_thread_memory():
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return {}

    return {}


def save_thread_memory(memory_data):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as file:
            json.dump(
                memory_data,
                file,
                indent=4,
                ensure_ascii=False
            )

    except Exception as error:
        print(f"Memory Sync Error: {str(error)}")


GEMINI_EMBEDDING_KEY = os.getenv("GEMINI_KEY_1")

if not GEMINI_EMBEDDING_KEY:
    raise ConfigurationError(
        "GEMINI_KEY_1 environment variable is missing."
    )


embedding_model = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-2",
    google_api_key=GEMINI_EMBEDDING_KEY,
    output_dimensionality=768
)



text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100
)


COLLECTION_NAME = "gigacorp_core_gemini_v2"





chroma_client = chromadb.EphemeralClient()


if os.path.exists("knowledge_base.docx"):

    base_loader = Docx2txtLoader(
        "knowledge_base.docx"
    )

    base_documents = base_loader.load()

    base_chunks = text_splitter.split_documents(
        base_documents
    )

    vector_db = Chroma.from_documents(
        documents=base_chunks,
        embedding=embedding_model,
        collection_name=COLLECTION_NAME,
        client=chroma_client
    )

else:

    vector_db = Chroma(
        embedding_function=embedding_model,
        collection_name=COLLECTION_NAME,
        client=chroma_client
    )


def get_pooled_llm_runtime(
    prompt_text,
    provider_allocation
):

    if provider_allocation["provider"] == "gemini":

        genai.configure(
            api_key=provider_allocation["key"]
        )

        model = genai.GenerativeModel(
            provider_allocation["model"]
        )

        response = model.generate_content(
            prompt_text
        )

        return response.text

    else:

        llm = ChatGroq(
            model=provider_allocation["model"],
            groq_api_key=provider_allocation["key"],
            temperature=0
        )

        response = llm.invoke(
            prompt_text
        )

        return response.content


@app.get("/")
async def health_check():

    return {
        "status": "ONLINE",
        "service": "GigaCorp Enterprise Support API",
        "version": "6.0.0"
    }


@app.post("/api/v1/support/upload")
async def upload_company_knowledge_pdf(
    file: UploadFile,
    case_id: str = Form(...)
):
    temp_file_path = None

    try:
        if (
            not file.filename
            or not file.filename.lower().endswith(".pdf")
        ):
            raise HTTPException(
                status_code=400,
                detail="Only PDF file formats are accepted."
            )

        safe_filename = (
            f"case_{case_id}_"
            f"{Path(file.filename).name}"
        )

        temp_file_path = (
            Path("/tmp") / safe_filename
        )

        with open(
            temp_file_path,
            "wb"
        ) as buffer:
            shutil.copyfileobj(
                file.file,
                buffer
            )

        pdf_loader = PyPDFLoader(
            str(temp_file_path)
        )

        pdf_documents = pdf_loader.load()

        pdf_chunks = (
            text_splitter.split_documents(
                pdf_documents
            )
        )

        for chunk in pdf_chunks:
            chunk.metadata["case_id"] = case_id

        vector_db.add_documents(
            pdf_chunks
        )

        return {
            "status": "SUCCESS",
            "message": (
                f"File {file.filename} compiled and "
                "appended to dynamic vector workspace."
            ),
            "chunks_ingested": len(pdf_chunks)
        }

    except HTTPException:
        raise

    except Exception as error:
        print(
            "\n"
            + "=" * 50
            + " BACKEND CRASH ERROR TRACE "
            + "=" * 50
        )

        traceback.print_exc()

        print("=" * 127 + "\n")

        raise HTTPException(
            status_code=500,
            detail=(
                "Ingestion lifecycle failed: "
                f"{str(error)}"
            )
        )

    finally:
        if (
            temp_file_path
            and temp_file_path.exists()
        ):
            try:
                temp_file_path.unlink()
            except Exception:
                pass


@app.post("/api/v1/support/chat")
async def process_customer_support_query(
    payload: ChatQueryRequest
):

    try:

        previous_history = ""

        case_id = payload.case_id

        chat_memory = load_thread_memory()


        if case_id in chat_memory:

            turns = chat_memory[case_id]

            for turn in turns[-3:]:

                previous_history += (
                    f"User: {turn['input']}\n"
                    f"Assistant: {turn['output']}\n"
                )


        retrieved_docs = (
            vector_db.similarity_search(
                payload.message,
                k=3,
                filter={
                    "case_id": case_id
                }
            )
        )


        if not retrieved_docs:

            retrieved_docs = (
                vector_db.similarity_search(
                    payload.message,
                    k=3
                )
            )


        context_block = "\n\n".join(
            document.page_content
            for document in retrieved_docs
        )


        full_system_prompt = (

            "You are an expert customer support assistant "
            "for GigaCorp Technologies.\n"

            "CRITICAL DIRECTIVE: Your response must be "
            "strictly concise, direct, and to-the-point. "
            "Answer ONLY what the user is currently asking. "
            "Do not summarize previous context or repeat "
            "user identity details unless explicitly requested.\n"

            "If the user asks a factual question about "
            "GigaCorp, provide only the factual answer "
            "from the retrieved context.\n"

            "If the user asks for a specific piece of "
            "information, reply with the direct answer "
            "without unnecessary conversational filler.\n"

            "Always cite the section title or heading "
            "from the context when providing corporate "
            "information.\n\n"

            f"Retrieved Context:\n"
            f"{context_block}\n\n"

            f"Previous Chat History:\n"
            f"{previous_history if previous_history else 'No previous interaction.'}\n\n"

            f"User's Current Question: "
            f"{payload.message}"
        )


        keys_pool = [

            {
                "provider": "gemini",
                "key": os.getenv("GEMINI_KEY_1"),
                "model": "gemini-1.5-flash"
            },

            {
                "provider": "gemini",
                "key": os.getenv("GEMINI_KEY_2"),
                "model": "gemini-1.5-flash"
            },

            {
                "provider": "groq",
                "key": os.getenv("GROQ_KEY_1"),
                "model": "llama-3.1-8b-instant"
            }

        ]


        execution_response_text = None


        for allocation in keys_pool:

            if allocation["key"]:

                try:

                    execution_response_text = (
                        get_pooled_llm_runtime(
                            full_system_prompt,
                            allocation
                        )
                    )


                    if execution_response_text:
                        break


                except Exception as provider_error:

                    print(
                        f"Provider Failure "
                        f"({allocation['provider']}): "
                        f"{str(provider_error)}"
                    )

                    continue


        if not execution_response_text:

            raise ConfigurationError(
                "Fallback API Key Pool exhausted."
            )


        if case_id not in chat_memory:

            chat_memory[case_id] = []


        chat_memory[case_id].append({

            "input": payload.message,

            "output": execution_response_text

        })


        save_thread_memory(
            chat_memory
        )


        return {

            "status": "SUCCESS",

            "case_id": case_id,

            "answer": execution_response_text,

            "citations_count": len(
                retrieved_docs
            )

        }


    except ConfigurationError as error:

        raise HTTPException(
            status_code=503,
            detail=str(error)
        )


    except Exception as error:

        print(
            "\n"
            + "=" * 50
            + " CHAT API CRASH TRACE "
            + "=" * 50
        )

        traceback.print_exc()

        print("=" * 122 + "\n")


        raise HTTPException(
            status_code=500,
            detail=str(error)
        )




if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                8000
            )
        )
    )