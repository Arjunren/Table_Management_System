# 1. Use the official Python image
FROM python:3.9-slim

# 2. Set the working directory
WORKDIR /app

# 3. Copy just the requirements first
COPY requirements.txt .

# 4. Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your web app code
COPY . .

# 6. Start the Flask application using Gunicorn
CMD gunicorn app:app --bind 0.0.0.0:$PORT