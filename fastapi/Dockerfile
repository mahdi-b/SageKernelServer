# Use an official Python runtime as a parent image
FROM python:3.9

# Set the working directory in the container to /app
WORKDIR /app

# Add the current directory contents into the container at /app
ADD . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 80 available to the world outside this container
EXPOSE 80


COPY id_rsa_github /root/.ssh/id_rsa
RUN chmod 600 /root/.ssh/id_rsa
RUN mkdir -p -m 0600 ~/.ssh && echo "StrictHostKeyChecking no" >> ~/.ssh/config

RUN git clone git@github.com:mahdi-b/SageKernelServer.git

EXPOSE 80

# Run app.py when the container launches
CMD ["python", "/app/SageKernelServer/src/main.py", "--host", "0.0.0.0", "--port", "80", "--url", "http://127.0.0.1:8888/?token=123456789"]
