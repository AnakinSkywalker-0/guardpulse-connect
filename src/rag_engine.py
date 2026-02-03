from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains import RetrievalQA
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "vectorstore/db_chroma"

def get_qa_chain():
    """
    Returns a QA chain that retrieves context from the vector store.
    """
    embedding_model = OpenAIEmbeddings()
    
    # Load the existing database
    db = Chroma(persist_directory=DB_PATH, embedding_function=embedding_model)
    retriever = db.as_retriever(search_kwargs={"k": 2})

    # Initialize LLM (GPT-3.5)
    llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)

    # Create RAG Chain
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True
    )
    
    return qa_chain