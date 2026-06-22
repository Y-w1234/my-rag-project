import os
from dotenv import load_dotenv

from langchain_community.document_loaders import TextLoader, PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.llms import Tongyi
from langchain.chains import RetrievalQA

load_dotenv()

# 全局变量，延迟初始化
vector_store = None
qa_chain = None

# 模型路径：优先使用本地下载的模型（从 ModelScope 下载），其次尝试 HF Hub
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCAL_MODEL_PATH = os.path.join(_BASE_DIR, "models", "sentence-transformers", "paraphrase-multilingual-MiniLM-L12-v2")
if os.path.exists(_LOCAL_MODEL_PATH):
    MODEL_NAME = _LOCAL_MODEL_PATH
    print(f"使用本地模型: {MODEL_NAME}")
else:
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    print(f"本地模型未找到，将从远程下载: {MODEL_NAME}")


def _get_embeddings():
    """获取 embedding 实例（单例）"""
    return HuggingFaceEmbeddings(model_name=MODEL_NAME)


def load_document(file_path):
    """加载指定路径的文档，支持 .txt, .pdf, .docx"""
    if file_path.endswith('.txt'):
        return TextLoader(file_path, encoding='utf-8').load()
    elif file_path.endswith('.pdf'):
        return PyPDFLoader(file_path).load()
    elif file_path.endswith('.docx'):
        return Docx2txtLoader(file_path).load()
    else:
        raise ValueError("不支持的文件格式，仅支持 .txt, .pdf, .docx")


def _load_all_documents(docs_dir):
    """从目录中加载所有支持的文档"""
    documents = []
    if not os.path.exists(docs_dir):
        return documents
    for file in os.listdir(docs_dir):
        file_path = os.path.join(docs_dir, file)
        if os.path.isfile(file_path):
            try:
                documents.extend(load_document(file_path))
                print(f"成功加载文档: {file}")
            except Exception as e:
                print(f"加载文档 {file} 失败: {e}")
    return documents


def get_vectorstore(docs_dir="./docs", persist_dir="./chroma_db"):
    """初始化向量数据库：从已有持久化数据恢复，或从文档目录新建"""
    embeddings = _get_embeddings()

    # 如果已有持久化的向量库，直接加载
    if os.path.exists(persist_dir) and os.path.isfile(os.path.join(persist_dir, "chroma.sqlite3")):
        vectorstore = Chroma(persist_directory=persist_dir, embedding_function=embeddings)
        print("成功加载已有向量数据库。")
        return vectorstore

    # 否则从文档目录新建
    print("未找到向量数据库，正在从文档创建...")
    documents = _load_all_documents(docs_dir)

    if not documents:
        raise ValueError(f"在 {docs_dir} 中没有找到可加载的文档。")

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(documents)
    print(f"文档已分割为 {len(chunks)} 个文本块。")

    vectorstore = Chroma.from_documents(documents=chunks, embedding=embeddings, persist_directory=persist_dir)
    print("向量数据库创建并持久化成功。")
    return vectorstore


def add_document_to_vectorstore(file_path, persist_dir="./chroma_db"):
    """将新文档添加到已有的向量库（增量更新）"""
    global vector_store

    if vector_store is None:
        raise RuntimeError("向量数据库尚未初始化，无法添加文档")

    # 加载并分割文档
    documents = load_document(file_path)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(documents)
    print(f"文档 '{os.path.basename(file_path)}' 已分割为 {len(chunks)} 个文本块。")

    # 添加到现有向量库（Chroma 会自动持久化）
    vector_store.add_documents(chunks)
    print(f"已将 {len(chunks)} 个文本块加入向量库，现在可以查询该文档了。")

    return len(chunks)


def rebuild_vectorstore(docs_dir="./docs", persist_dir="./chroma_db"):
    """完全重建向量库（删除旧的，从 docs 目录重新索引所有文档）"""
    global vector_store, qa_chain
    import shutil

    # 删除旧向量库
    if os.path.exists(persist_dir):
        shutil.rmtree(persist_dir)
        print("已删除旧向量数据库。")

    # 重新创建
    os.makedirs(persist_dir, exist_ok=True)
    vector_store = get_vectorstore(docs_dir, persist_dir)
    qa_chain = get_qa_chain(vector_store)
    print("向量库完全重建完成！")
    return vector_store, qa_chain


def get_qa_chain(vectorstore):
    """基于向量数据库和大模型创建问答链"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("请在 .env 文件中配置 DASHSCOPE_API_KEY")

    llm = Tongyi(
        model_name="qwen-max",
        dashscope_api_key=api_key
    )

    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True
    )
    return qa_chain


def initialize_rag():
    """初始化 RAG 系统（在 FastAPI 启动时调用）"""
    global vector_store, qa_chain
    print("正在初始化 RAG 系统...")
    vector_store = get_vectorstore()
    qa_chain = get_qa_chain(vector_store)
    print("RAG 系统初始化完成！")
    return vector_store, qa_chain
