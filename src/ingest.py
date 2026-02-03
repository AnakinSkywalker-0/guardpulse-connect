import os
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

# Configuration
DATA_PATH = "data/"
DB_PATH = "vectorstore/db_chroma"

def create_vector_db():
    """
    Ingests documents from the data directory and creates a vector store.
    """
    print(f"Loading documents from {DATA_PATH}...")
    
    documents = []
    # Load all .txt files
    for file in os.listdir(DATA_PATH):
        if file.endswith(".txt"):
            loader = TextLoader(os.path.join(DATA_PATH, file))
            documents.extend(loader.load())
            
    if not documents:
        print("No documents found in data/ folder.")
        return

    # Split text into chunks (simulating standard RAG preprocessing)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    texts = text_splitter.split_documents(documents)

    print(f"Split into {len(texts)} chunks. Creating embeddings...")

    # Create Vector Store
    # Note: Requires OPENAI_API_KEY in .env, or swap with HuggingFaceEmbeddings for free version
    embedding_model = OpenAIEmbeddings()
    
    db = Chroma.from_documents(documents=texts, embedding=embedding_model, persist_directory=DB_PATH)
    print(f"Vector Database created at {DB_PATH}")

if __name__ == "__main__":
    create_vector_db()