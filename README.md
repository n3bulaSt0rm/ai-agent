# AI-Powered Knowledge Management Platform

An intelligent platform designed to help you manage, search, and derive insights from your documents and emails. This project leverages Retrieval-Augmented Generation (RAG) to provide a powerful semantic search experience, transforming your personal or enterprise data into a queryable knowledge base.

## ✨ Key Features

-   **📄 Intelligent Document Processing:** Upload and manage various document formats. The system automatically extracts text and metadata.
-   **📧 Gmail Integration:** Securely connect your Gmail account to index emails and attachments, incorporating your communications into the knowledge base.
-   **🧠 AI-Powered Semantic Search:** Go beyond keyword matching. Ask questions in natural language and get precise answers based on the content of your files and emails.
-   **🔐 Secure Authentication:** User management and authentication system to protect your data.
-   **🚀 Scalable Architecture:** Built on a modern microservices architecture to handle large volumes of data and user requests efficiently.
-   **💻 User-Friendly Interface:** A clean and intuitive web interface built with React for a seamless user experience.

## 🏛️ Architecture

The platform is designed with a scalable and decoupled microservices architecture, ensuring high performance and maintainability.

-   **Frontend:** A responsive web application built with **React** that provides the user interface for file management and search.
-   **Backend Services:**
    -   **Web Service:** A lightweight API gateway that handles HTTP requests, user authentication, and serves as the primary entry point.
    -   **Processing Service:** A set of asynchronous workers responsible for the heavy lifting: consuming data from ingestion sources, processing files, generating embeddings, and storing them.
    -   **Message Queue (RabbitMQ):** Decouples the Web Service from the Processing Service, allowing for resilient and scalable background job processing.
-   **AI Core (RAG Pipeline):** The heart of the intelligent search. It uses a multi-stage process to ingest data, convert it into searchable vectors, and retrieve relevant context to answer user queries.
-   **Data Stores:**
    -   **Qdrant:** A high-performance vector database used to store and search through document embeddings.
    -   **Relational Database:** Stores metadata about users, files, and processing status.

## 🛠️ Technology Stack

-   **Frontend:** React, Vite, CSS
-   **Backend:** Python, FastAPI
-   **AI/ML:** Gemini, Hugging Face Transformers
-   **Database:** Qdrant, PostgreSQL/SQLite
-   **Messaging:** RabbitMQ
-   **Containerization:** Docker, Docker Compose

## 🚀 Getting Started

Follow these steps to get the project up and running on your local machine.

### Prerequisites

-   [Docker](https://www.docker.com/get-started) & Docker Compose
-   [Python](https://www.python.org/downloads/) 3.9+
-   [Node.js](https://nodejs.org/en/download/) & npm

### 1. Clone & Configure

First, clone the repository and set up your environment variables.

```bash
git clone <your-repository-url>
cd ai-agent
# Copy the example environment file
cp env.example .env
```

Now, open `.env` and fill in the required API keys and configuration details. Ensure `FRONTEND_URL` matches the address of your frontend application (e.g., `http://localhost:5173`).

### 2. Manual Installation

Follow these steps to run each service manually.

<details>
<summary><strong>1. Launch Qdrant Vector Database</strong></summary>

Run the Qdrant container. This will store the vector embeddings for your documents.

```bash
docker run -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_data:/qdrant/storage \
    qdrant/qdrant
```
</details>

<details>
<summary><strong>2. Launch Backend Services</strong></summary>

Open a new terminal, navigate to the `backend` directory, set up a virtual environment, and install dependencies.

```bash
cd backend
python -m venv venv
# Activate virtual environment
# Windows: .\venv\Scripts\activate | macOS/Linux: source venv/bin/activate
pip install -r ../requirements.txt
```

Then, run the web and processing services. **Each command needs to be run in a separate terminal window.**

```bash
# Terminal 1: Run the Web Service
python cmd/web_service.py
```
```bash
# Terminal 2: Run the Processing Service
python cmd/processing_service.py
```
</details>

<details>
<summary><strong>3. Launch Frontend Application</strong></summary>

Open a third terminal, navigate to the `frontend` directory, install dependencies, and start the development server.

```bash
cd frontend
npm install
npm run dev
```

You can now access the application at **http://localhost:5173** (or the port shown in the terminal).
</details>

### 3. Stopping the Application

To stop the application, press `Ctrl + C` in each of the terminal windows.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
