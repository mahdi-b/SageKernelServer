import uuid
import time
import asyncio
from jupyter_client.kernelspec import KernelSpecManager
import uvicorn
import websockets
from fastapi import FastAPI, WebSocket, HTTPException
import requests
import json
import argparse
from urllib.parse import urlparse, urlunparse, urljoin
import re
from typing import Optional
import pika
from typing import Dict, Union
from pydantic import BaseModel

max_number_kernels = 3
output_checking_interval = 0.1
rabbit_mq_host = "localhost"


app = FastAPI()

parser = argparse.ArgumentParser(description='Your Flask app')
parser.add_argument('--url', type=str, help='URL to be used in routes')
args = parser.parse_args()

# Set the URL

full_url = args.url



# Validate the URL and the token
parsed_url = urlparse(full_url)
if not all([parsed_url.scheme, parsed_url.netloc, parsed_url.query]):
    raise ValueError("Invalid URL")

base_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))
ws_base_url = parsed_url._replace(scheme="ws")
ws_base_url = urlunparse(ws_base_url)

token = parsed_url.query.split('=')[-1]
if not re.match(r'^token=\w{4,}$', parsed_url.query):
    raise ValueError("Invalid token")

kernel_websockets: Dict[str, WebSocket] = {}
session_to_kernel: Dict[str, str] = {}


def get_all_kernel_specs():
    kernel_spec_manager = KernelSpecManager()
    return kernel_spec_manager.get_all_specs()




class PartialExecBody(BaseModel):
    session: Union[str, None] = None
    code: str


from pydantic import BaseModel
import time
import json

def rabbitmq_connect():
    # Connect to RabbitMQ server
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=rabbit_mq_host, heartbeat=0))
    return connection


class ExecOutput(BaseModel):
    session_id: str
    start_time: str
    end_time: Optional[str]
    msg_type: Optional[str]
    content: str = {}
    execution_count: int = 0
    completed: bool = False


outputs: dict[str, ExecOutput] = {}
rabbitmq_connection = rabbitmq_connect()

async def check_messages(websocket, rabbitmq_connection):
    channel = rabbitmq_connection.channel()
    channel.exchange_declare(exchange='jupyter', exchange_type='topic')

    while True:
        message = await websocket.recv()
        message_data = json.loads(message)
        print(message_data)
        if "parent_header" in message_data:

            msg_id = message_data["parent_header"]["msg_id"]
            session_id = message_data["parent_header"]["session"]
            start_time = message_data["parent_header"]["date"]
            # ignore messages that we didn't send.
            # e.g., spontaneous messages from the kernel or
            # sent through other means
            if msg_id not in outputs:
                continue

            if outputs[msg_id] is None:
                outputs[msg_id] = ExecOutput(session_id=session_id, start_time=start_time, end_time=None,
                                                     msg_type=None, data='')

            if message_data["channel"] == "shell":
                outputs[msg_id].msg_type = message_data['metadata']['status']
                outputs[msg_id].end_time = time.time()
                outputs[msg_id].execution_count = message_data["content"]["execution_count"]


            if "execution_state" in message_data["content"] and \
                    message_data["content"]["execution_state"] == "idle" \
                    and msg_id in outputs:
                outputs[msg_id].completed = True
                print("Publishing now...")
                channel.basic_publish(
                    exchange='jupyter',
                    routing_key=session_id,
                    body=f"Message {msg_id} just completed. {outputs[msg_id].content}"
                )

            if message_data["msg_type"] in ["stream", "display_data", "execute_result", "error"]:
                # Extract output and append to existing output
                output_data = message_data["content"].get("data")
                if output_data is not None:
                    for key, val in output_data.items():
                        outputs[msg_id].content[key] = outputs[msg_id].content.get(key, '') + val
                elif 'text' in message_data["content"]:
                    key = message_data["content"]['name']
                    val = message_data["content"]['text']
                    outputs[msg_id].content[key] = outputs[msg_id].content.get(key, '') + val
                elif "traceback" in message_data["content"]:
                    for key in ["traceback", "ename", "evalue"]:
                        outputs[msg_id].content[key] = message_data["content"][key]
                print("Publishing now...")
                channel.basic_publish(
                    exchange='jupyter',
                    routing_key=session_id,
                    body=f"Message {msg_id}  has an ouput. {outputs[msg_id].content}"
                )



        print(f"*** outputs: {outputs}")

    return outputs


@app.get("/kernel")
def get_kernels():
    # list the kernels created by the user
    url = urljoin(base_url, "/api/kernels")
    # Get the XSRF token
    session = requests.Session()
    response = session.get(base_url)
    xsrf_token = response.cookies.get('_xsrf')

    headers = {
        'Authorization': f'token {token}',
        "X-XSRFToken": xsrf_token,
        "Referer": base_url
    }
    response = requests.post(url, headers=headers, json={})
    if response.status_code != 201:
        print (response.status_code)
        raise HTTPException(status_code=500, detail=f"Failed to get kernels {response.text}")
    elif response.status_code == 201:
        return response.json()
    else:
        raise HTTPException(status_code=500, detail=f"Failed to get kernels {response.text}")


@app.post("/kernel/{kernel_name}")
async def create_kernel(kernel_name: str):
    if len(kernel_websockets) == max_number_kernels:
        print("1")
        raise HTTPException(status_code=400,
                            detail=f"Maximum number of kernels reached. Please delete one of the existing kernels.")

    url = urljoin(base_url, "/api/kernels")
    if not kernel_name:
        print("2")
        raise HTTPException(status_code=400, detail="Missing kernel_name")

    # Get the XSRF token
    session = requests.Session()
    response = session.get(base_url)
    xsrf_token = response.cookies.get('_xsrf')

    headers = {
        'Authorization': f'token {token}',
        "X-XSRFToken": xsrf_token,
        "Referer": base_url
    }

    kernel_specs_url = urljoin(base_url, "/api/kernelspecs")
    response = requests.get(kernel_specs_url, headers=headers)
    if response.status_code != 201:
        kernel_specs = response.json()['kernelspecs']
    else:
        raise HTTPException(status_code=500, detail=f"Failed to get kernelspecs {response.text}")

    if kernel_name not in kernel_specs:
        raise HTTPException(status_code=400, detail=f"Not a valid kernel_name. Valid values are: {list(kernel_specs.keys())}")

    response = requests.post(url, headers=headers, json={"name": kernel_name})

    if response.status_code != 201:
        raise HTTPException(status_code=500, detail=f"Failed to create kernel {response.text}")
    elif response.status_code == 201:
        print(f'Successfully created kernel {kernel_name}')
        kernel_id = response.json()['id']
        kernel_websockets[kernel_id] = None
        print(kernel_websockets)
        # headers = {'Authorization': f'token {token}'}
        session_id = str(uuid.uuid4())
        ws_url = urljoin(ws_base_url, f"/api/kernels/{kernel_id}/channels?session_id={session_id}")

        kernel_websockets[kernel_id] = await websockets.connect(ws_url, extra_headers=headers)
        asyncio.create_task(check_messages(kernel_websockets[kernel_id], rabbitmq_connection))
        response_object = response.json()
        response_object.update({"session_id": session_id})
        return response_object
    else:
        raise HTTPException(status_code=500, detail=f"Failed to create kernel {response.text}")

@app.delete("/kernel/{kernel_id}")
async def delete_kernel(kernel_id: str):
    # Get the XSRF token
    session = requests.Session()
    response = session.get(base_url)
    xsrf_token = response.cookies.get('_xsrf')

    if kernel_id not in kernel_websockets:
        raise HTTPException(status_code=400, detail="Kernel not started")

    headers = {
        'Authorization': f'token {token}',
        "X-XSRFToken": xsrf_token,
        "Referer": base_url
    }
    print(headers)
    url = urljoin(base_url, f"/api/kernels/{kernel_id}")
    response = requests.delete(url, headers=headers)

    if response.status_code == 204:
        print(f'Successfully deleted kernel {kernel_id}')
        try:
            del kernel_websockets[kernel_id]
        except KeyError:
            print(f"{kernel_id} not found in kernel_websockets.")
        return {"kernel_id": kernel_id, "status": "deleted"}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to delete kernel {response.text}")



@app.post("/execute/{kernel_id}")
async def execute_code(kernel_id: str, body: PartialExecBody):

    print(f"About to run Code {body.code} on kernel {kernel_id}")

    global kernel_websockets
    print(kernel_websockets)

    if kernel_id not in kernel_websockets:
        raise HTTPException(status_code=400, detail="Cannot execute code. Kernel not started")

    session_id = body.session
    if session_id is None:
        session_id = str(uuid.uuid4())
    session_to_kernel[session_id] = kernel_id

    ws_url = urljoin(ws_base_url, f"/api/kernels/{kernel_id}/channels?session_id={session_id}")

    if kernel_websockets[kernel_id] is None or kernel_websockets[kernel_id].closed:
        headers = {'Authorization': f'token {token}'}
        kernel_websockets[kernel_id] = await websockets.connect(ws_url, extra_headers=headers)

        # create a task with the sole purpose of keeping the connection alive
        asyncio.create_task(check_messages(kernel_id, kernel_websockets[kernel_id]))

        print(f"Connected to kernel {kernel_id}")

    msg_id = str(uuid.uuid4())
    print("msg_id = ", msg_id)

    message = {
        'header': {
            'msg_id': msg_id,
            'username': 'test',
            'session': session_id,
            'msg_type': 'execute_request',
            'version': '5.0'
        },
        'parent_header': {},
        'metadata': {},
        'content': {
            'code': body.code,
            'silent': False,
            'store_history': True,
            'user_expressions': {},
            'allow_stdin': True,
            'allow_stdout': True,
            'stop_on_error': True
        },
        'buffers': [],
        "channel": "shell"
    }
    await kernel_websockets[kernel_id].send(json.dumps(message))
    outputs[msg_id] = None
    return {"msg_id": msg_id}

@app.post("/stop/{kernel_id}")
async def stop_kernel(kernel_id: str):
    print(f"Stopping kernel {kernel_id}")
    if kernel_id not in kernel_websockets:
        raise HTTPException(status_code=400, detail="Kernel not started")
    ws = kernel_websockets[kernel_id]
    await ws.close()
    del kernel_websockets[kernel_id]

@app.get("/status/{msg_id}")
async def execute_code(msg_id: str):
    # Getting message from users.
    if msg_id not in outputs:
        raise HTTPException(status_code=400, detail="Invalid msg_id")
    else:
        print(outputs[msg_id].json())
    return outputs[msg_id].dict()

@app.on_event("shutdown")
async def shutdown_event():
    print("Cleaning up before shutdown")
    for kernel_id, ws in kernel_websockets.items():
        try:
            if ws is not None and not ws.closed:
                await ws.close()
        except Exception as e:
            print(f"Error closing websocket for kernel {kernel_id}")





if __name__ == "__main__":

    uvicorn.run('main:app', host="0.0.0.0", port=8000, reload=True)