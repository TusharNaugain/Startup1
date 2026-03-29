# How to Run Liberty App with Docker

This guide explains how to run the Liberty Classifier application using Docker. This ensures compatibility and ease of use.

## Prerequisites

1.  **Install Docker Desktop**:
    *   Download and install Docker Desktop for your system (Windows or Mac): [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
    *   After installing, **open Docker Desktop** and make sure it is running.

---

## Part 1: Running It Locally (For Testing)

1.  Open Terminal (Mac) or Command Prompt (Windows).
2.  Navigate to the project folder:
    ```bash
    cd /path/to/Liberty_Folder
    ```
3.  Start the Application:
    ```bash
    docker-compose up --build
    ```
4.  Open in Browser: [http://localhost:5000](http://localhost:5000)

---

## Part 2: Publishing for Others (For You)

To share this app so others can run it without the source code, you need to **publish** it to Docker Hub.

### Step 1: Create Docker Hub Account
Go to [https://hub.docker.com/](https://hub.docker.com/) and create a free account. Remember your **username**.

### Step 2: Run Publish Script
In your terminal (inside the project folder), run:

```bash
./publish.sh
```
*(On Windows, you may need to use Git Bash or install WSL, or manually run the docker commands inside the script)*

1.  It will ask for your **Docker Hub Username**.
2.  It will ask for your **Password** (login).
3.  It will build and upload the app to the cloud.

---

## Part 3: How Others Can Run It

Once published, share this single command with your team. They **do not** need the code, only Docker Desktop.

Replace `YOUR_USERNAME` with your actual Docker Hub username:

```bash
docker run -p 5000:5000 YOUR_USERNAME/liberty-classifier:latest
```

They can then open [http://localhost:5000](http://localhost:5000) to use the app.
