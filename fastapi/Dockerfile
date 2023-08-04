FROM python:3.9

RUN apt-get update && apt-get install -y iputils-ping


WORKDIR /app
ADD . /app


EXPOSE 8000


# RUN git clone https://github.com/mahdi-b/SageKernelServer.git

COPY . /app/SageKernelServer/fastapi

WORKDIR /app/SageKernelServer/fastapi
RUN pip install --no-cache-dir -r requirements.txt


COPY start.sh /app/SageKernelServer/
RUN chmod +x /app/SageKernelServer/start.sh


ENTRYPOINT ["/app/SageKernelServer/start.sh"]