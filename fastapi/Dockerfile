FROM python:3.9

RUN apt-get update && apt-get install -y iputils-ping


WORKDIR /app
ADD . /app


EXPOSE 80

COPY id_rsa_github /root/.ssh/id_rsa
RUN chmod 600 /root/.ssh/id_rsa
RUN mkdir -p -m 0600 ~/.ssh && echo "StrictHostKeyChecking no" >> ~/.ssh/config

RUN git clone git@github.com:mahdi-b/SageKernelServer.git
WORKDIR /app/SageKernelServer/fastapi
RUN pip install --no-cache-dir -r requirements.txt


COPY start.sh /app/SageKernelServer/
RUN chmod +x /app/SageKernelServer/start.sh


ENTRYPOINT ["/app/SageKernelServer/start.sh"]