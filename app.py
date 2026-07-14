import os
import shutil
import tempfile
import traceback
from pathlib import Path

import psycopg2
import google.generativeai as genai

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    Form
)

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from langchain_groq import ChatGroq

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter
)

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader
)

from langchain_google_genai import (
    GoogleGenerativeAIEmbeddings
)


load_dotenv()


# ============================================================
# FASTAPI APPLICATION
# ============================================================


app = FastAPI(
    title="GigaCorp Enterprise Support API Engine",
    version="7.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# REQUEST MODELS
# ============================================================


class ChatQueryRequest(BaseModel):
    case_id: str
    message: str


class ConfigurationError(Exception):
    pass


# ============================================================
# ENVIRONMENT CONFIGURATION
# ============================================================


DATABASE_URL = os.getenv("DATABASE_URL")

GEMINI_EMBEDDING_KEY = os.getenv(
    "GEMINI_KEY_1"
)


if not DATABASE_URL:
    raise ConfigurationError(
        "DATABASE_URL environment variable is missing."
    )


if not GEMINI_EMBEDDING_KEY:
    raise ConfigurationError(
        "GEMINI_KEY_1 environment variable is missing."
    )


# ============================================================
# DATABASE CONNECTION
# ============================================================


def get_database_connection():

    return psycopg2.connect(
        DATABASE_URL
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================


def initialize_database():

    connection = get_database_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            CREATE EXTENSION IF NOT EXISTS vector;
            """
        )


        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_documents
            (
                id BIGSERIAL PRIMARY KEY,

                case_id TEXT,

                content TEXT NOT NULL,

                source TEXT,

                embedding VECTOR(768) NOT NULL,

                created_at TIMESTAMPTZ
                DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_memory
            (
                id BIGSERIAL PRIMARY KEY,

                case_id TEXT NOT NULL,

                user_input TEXT NOT NULL,

                assistant_output TEXT NOT NULL,

                created_at TIMESTAMPTZ
                DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_knowledge_documents_case_id

            ON knowledge_documents(case_id);
            """
        )


        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_chat_memory_case_id

            ON chat_memory(case_id);
            """
        )


        connection.commit()


    except Exception:

        connection.rollback()

        raise


    finally:

        cursor.close()

        connection.close()


initialize_database()


# ============================================================
# EMBEDDING MODEL
# ============================================================


embedding_model = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-2",
    google_api_key=GEMINI_EMBEDDING_KEY,
    output_dimensionality=768
)


# ============================================================
# TEXT SPLITTER
# ============================================================


text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100
)


# ============================================================
# VECTOR HELPERS
# ============================================================


def vector_to_postgres(
    embedding
):

    return (
        "["
        + ",".join(
            str(float(value))
            for value in embedding
        )
        + "]"
    )


# ============================================================
# DOCUMENT STORAGE
# ============================================================


def add_documents_to_database(
    documents,
    case_id=None,
    source=None
):

    if not documents:
        return 0


    document_texts = [

        document.page_content

        for document in documents

    ]


    embeddings = (
        embedding_model.embed_documents(
            document_texts
        )
    )


    connection = get_database_connection()

    cursor = connection.cursor()


    try:

        for document, embedding in zip(
            documents,
            embeddings
        ):

            cursor.execute(
                """
                INSERT INTO knowledge_documents
                (
                    case_id,
                    content,
                    source,
                    embedding
                )

                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s::vector
                );
                """,
                (
                    case_id,
                    document.page_content,
                    source,
                    vector_to_postgres(
                        embedding
                    )
                )
            )


        connection.commit()


        return len(documents)


    except Exception:

        connection.rollback()

        raise


    finally:

        cursor.close()

        connection.close()


# ============================================================
# VECTOR SIMILARITY SEARCH
# ============================================================


def similarity_search(
    query,
    case_id=None,
    limit=3
):

    query_embedding = (
        embedding_model.embed_query(
            query
        )
    )


    postgres_vector = vector_to_postgres(
        query_embedding
    )


    connection = get_database_connection()

    cursor = connection.cursor()


    try:

        if case_id:

            cursor.execute(
                """
                SELECT
                    content,
                    source

                FROM knowledge_documents

                WHERE case_id = %s

                ORDER BY
                    embedding <=> %s::vector

                LIMIT %s;
                """,
                (
                    case_id,
                    postgres_vector,
                    limit
                )
            )


        else:

            cursor.execute(
                """
                SELECT
                    content,
                    source

                FROM knowledge_documents

                ORDER BY
                    embedding <=> %s::vector

                LIMIT %s;
                """,
                (
                    postgres_vector,
                    limit
                )
            )


        rows = cursor.fetchall()


        return [

            {
                "content": row[0],
                "source": row[1]
            }

            for row in rows

        ]


    finally:

        cursor.close()

        connection.close()


# ============================================================
# CHAT MEMORY
# ============================================================


def load_thread_memory(
    case_id,
    limit=3
):

    connection = get_database_connection()

    cursor = connection.cursor()


    try:

        cursor.execute(
            """
            SELECT
                user_input,
                assistant_output

            FROM chat_memory

            WHERE case_id = %s

            ORDER BY id DESC

            LIMIT %s;
            """,
            (
                case_id,
                limit
            )
        )


        rows = cursor.fetchall()

        rows.reverse()


        return [

            {
                "input": row[0],
                "output": row[1]
            }

            for row in rows

        ]


    finally:

        cursor.close()

        connection.close()


def save_thread_memory(
    case_id,
    user_input,
    assistant_output
):

    connection = get_database_connection()

    cursor = connection.cursor()


    try:

        cursor.execute(
            """
            INSERT INTO chat_memory
            (
                case_id,
                user_input,
                assistant_output
            )

            VALUES
            (
                %s,
                %s,
                %s
            );
            """,
            (
                case_id,
                user_input,
                assistant_output
            )
        )


        connection.commit()


    except Exception:

        connection.rollback()

        raise


    finally:

        cursor.close()

        connection.close()


# ============================================================
# BASE KNOWLEDGE INITIALIZATION
# ============================================================


def initialize_base_knowledge():

    knowledge_file = Path(
        "knowledge_base.docx"
    )


    if not knowledge_file.exists():

        return


    connection = get_database_connection()

    cursor = connection.cursor()


    try:

        cursor.execute(
            """
            SELECT COUNT(*)

            FROM knowledge_documents

            WHERE source = %s;
            """,
            (
                "knowledge_base.docx",
            )
        )


        existing_documents = (
            cursor.fetchone()[0]
        )


    finally:

        cursor.close()

        connection.close()


    if existing_documents > 0:

        print(
            "Base knowledge already initialized."
        )

        return


    print(
        "Initializing base knowledge..."
    )


    base_loader = Docx2txtLoader(
        str(knowledge_file)
    )


    base_documents = (
        base_loader.load()
    )


    base_chunks = (
        text_splitter.split_documents(
            base_documents
        )
    )


    add_documents_to_database(
        documents=base_chunks,
        case_id=None,
        source="knowledge_base.docx"
    )


    print(
        f"Base knowledge initialized: "
        f"{len(base_chunks)} chunks."
    )


initialize_base_knowledge()


# ============================================================
# LLM PROVIDER POOL
# ============================================================


def get_pooled_llm_runtime(
    prompt_text,
    provider_allocation
):

    if (
        provider_allocation["provider"]
        == "gemini"
    ):

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


    llm = ChatGroq(
        model=provider_allocation["model"],
        groq_api_key=provider_allocation["key"],
        temperature=0
    )


    response = llm.invoke(
        prompt_text
    )


    return response.content


# ============================================================
# HEALTH CHECK
# ============================================================


@app.get("/")
async def health_check():

    return {
        "status": "ONLINE",
        "service": (
            "GigaCorp Enterprise Support API"
        ),
        "version": "7.0.0",
        "database": "Neon PostgreSQL",
        "vector_engine": "pgvector"
    }


# ============================================================
# PDF KNOWLEDGE UPLOAD
# ============================================================


@app.post(
    "/api/v1/support/upload"
)
async def upload_company_knowledge_pdf(
    file: UploadFile,
    case_id: str = Form(...)
):

    temp_file_path = None


    try:

        if (
            not file.filename
            or not file.filename
            .lower()
            .endswith(".pdf")
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "Only PDF file formats "
                    "are accepted."
                )
            )


        safe_filename = (
            f"case_{case_id}_"
            f"{Path(file.filename).name}"
        )


        temp_file_path = (
            Path(
                tempfile.gettempdir()
            )
            / safe_filename
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


        pdf_documents = (
            pdf_loader.load()
        )


        pdf_chunks = (
            text_splitter.split_documents(
                pdf_documents
            )
        )


        chunks_ingested = (
            add_documents_to_database(
                documents=pdf_chunks,
                case_id=case_id,
                source=file.filename
            )
        )


        return {
            "status": "SUCCESS",
            "message": (
                f"File {file.filename} compiled "
                "and stored in Neon pgvector."
            ),
            "chunks_ingested": (
                chunks_ingested
            )
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


        print(
            "=" * 127
            + "\n"
        )


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


# ============================================================
# CUSTOMER SUPPORT CHAT
# ============================================================


@app.post(
    "/api/v1/support/chat"
)
async def process_customer_support_query(
    payload: ChatQueryRequest
):

    try:

        previous_history = ""

        case_id = payload.case_id


        chat_history = load_thread_memory(
            case_id=case_id,
            limit=3
        )


        for turn in chat_history:

            previous_history += (
                f"User: {turn['input']}\n"
                f"Assistant: "
                f"{turn['output']}\n"
            )


        retrieved_docs = similarity_search(
            query=payload.message,
            case_id=case_id,
            limit=3
        )


        if not retrieved_docs:

            retrieved_docs = (
                similarity_search(
                    query=payload.message,
                    limit=3
                )
            )


        context_block = "\n\n".join(

            document["content"]

            for document in retrieved_docs

        )


        full_system_prompt = (

            "You are an expert customer support "
            "assistant for GigaCorp Technologies.\n"

            "CRITICAL DIRECTIVE: Your response "
            "must be strictly concise, direct, "
            "and to-the-point. "

            "Answer ONLY what the user is "
            "currently asking. "

            "Do not summarize previous context "
            "or repeat user identity details "
            "unless explicitly requested.\n"

            "If the user asks a factual question "
            "about GigaCorp, provide only the "
            "factual answer from the retrieved "
            "context.\n"

            "If the user asks for a specific "
            "piece of information, reply with "
            "the direct answer without unnecessary "
            "conversational filler.\n"

            "Always cite the section title or "
            "heading from the context when "
            "providing corporate information.\n\n"

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
                "key": os.getenv(
                    "GEMINI_KEY_1"
                ),
                "model": (
                    "gemini-1.5-flash"
                )
            },

            {
                "provider": "gemini",
                "key": os.getenv(
                    "GEMINI_KEY_2"
                ),
                "model": (
                    "gemini-1.5-flash"
                )
            },

            {
                "provider": "groq",
                "key": os.getenv(
                    "GROQ_KEY_1"
                ),
                "model": (
                    "llama-3.1-8b-instant"
                )
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


        save_thread_memory(
            case_id=case_id,
            user_input=payload.message,
            assistant_output=(
                execution_response_text
            )
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


        print(
            "=" * 122
            + "\n"
        )


        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================


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