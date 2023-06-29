# Use an official Python runtime as a parent image
FROM python:3.9

# Set the working directory in the container to /app
WORKDIR /app

# Add the current directory contents into the container at /app
ADD . /app

# Make port 80 available to the world outside this container
EXPOSE 80

COPY id_rsa_github /root/.ssh/id_rsa
RUN chmod 600 /root/.ssh/id_rsa
RUN mkdir -p -m 0600 ~/.ssh && echo "StrictHostKeyChecking no" >> ~/.ssh/config

RUN git clone git@github.com:mahdi-b/SageKernelServer.git
WORKDIR /app/SageKernelServer/fastapi
RUN pip install --no-cache-dir -r requirements.txt

# Copy the start.sh script to the container and make it executable
COPY start.sh /app/SageKernelServer/
RUN chmod +x /app/SageKernelServer/start.sh

# Use start.sh as the entry point
ENTRYPOINT ["/app/SageKernelServer/start.sh"]