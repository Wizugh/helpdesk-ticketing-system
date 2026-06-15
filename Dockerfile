# Use the official slim Python image to keep the image size small
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements first so Docker can cache the pip install layer.
# If only app code changes, this layer won't be rebuilt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application source code
COPY . .

# Document the port the app listens on (does not publish it — that's docker run -p)
EXPOSE 5000

CMD ["python", "app.py"]
