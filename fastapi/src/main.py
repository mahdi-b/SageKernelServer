import uuid
import time
from datetime import datetime
from dotenv import load_dotenv
import asyncio
from jupyter_client.kernelspec import KernelSpecManager
import uvicorn
import websockets
from fastapi import FastAPI, WebSocket, HTTPException, Request
import requests
import json
import argparse
from urllib.parse import urlparse, urlunparse, urljoin
import re
from typing import Optional, List
import pika
from typing import Dict, Union
from pydantic import BaseModel, Field
import os

from sse_starlette.sse import EventSourceResponse
from fastapi.middleware.cors import CORSMiddleware


# rabbit_mq_host = f"amqp://guest:guest@0.0.0.0:5672/?heartbeat=0"
# rabbit_mq_host = "127.0.0.1"

max_number_kernels = 3
output_checking_interval = 0.1

STREAM_DELAY = 0.01  # second
RETRY_TIMEOUT = 15000  # milisecond

app = FastAPI()
# origins = [
#     "*",
# ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True, # Allows cookies/authorization headers
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)



parser = argparse.ArgumentParser(description='SageKernelServer')
parser.add_argument('--url', type=str, help='URL to be used in routes')
args = parser.parse_args()

# Set the URL

full_url = args.url


# Validate the URL and the token
parsed_url = urlparse(full_url)
if not all([parsed_url.scheme, parsed_url.netloc, parsed_url.query]):
    raise ValueError("Invalid URL")

base_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))
# TODO: do this if we're using the RabbitMQ server for communication
# ws_base_url = None
# if os.getenv("messaging_type") == "rabbitmq":
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

# from pydantic import BaseModel
# import time
# import json

# def rabbitmq_connect():
#     # Connect to RabbitMQ server
#     connection = pika.BlockingConnection(
#         pika.ConnectionParameters(host=rabbit_mq_host, heartbeat=0))
#     return connection



# def rabbitmq_connect():
#     attempts = 2
#     for i in range(attempts):
#         try:
#             connection = pika.BlockingConnection(
#                 pika.ConnectionParameters(
#                     host=rabbit_mq_host,
#                     heartbeat=0,
#                     blocked_connection_timeout=60,
#                 )
#             )
#             return connection
#         except pika.exceptions.AMQPConnectionError:
#             if i < attempts - 1:  # i is zero indexed
#                 time.sleep(10)  # wait for 10 seconds before trying to reconnect
#                 continue
#             else:
#                 raise


class ExecOutput(BaseModel):
    session_id: str
    start_time: str
    end_time: Optional[str]
    msg_type: Optional[str]
    content: List[Dict[str, str]] = []
    last_update_time: Optional[str] = None
    execution_count: int = 0
    completed: bool = False

class KernelInfo(BaseModel):
    kernel_id: Optional[str] = None
    # room: str
    # board: str
    name: str
    # alias: str
    # is_private: bool
    # owner: str

outputs: dict[str, ExecOutput] = {}
kernel_info_collection: dict[str, KernelInfo] = {}
# rabbitmq_connection = rabbitmq_connect()


# async def check_messages(websocket, rabbitmq_connection):
async def check_messages(websocket):
    # channel = rabbitmq_connection.channel()
    # channel.exchange_declare(exchange='jupyter', exchange_type='topic')

    while True:
        print("before receive messge")
        try:
            message = await websocket.recv()
        except Exception as e:
            print(e)

            # Make sure you send back and error
            outputs[msg_id] = ExecOutput(session_id=session_id, start_time=start_time, end_time=start_time,
                                         msg_type='', data=None)
            outputs[msg_id].completed = True



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

            if outputs[msg_id] == {}:
                outputs[msg_id] = ExecOutput(session_id=session_id, start_time=start_time, end_time=None,
                                                     msg_type=None, data='')

            if message_data["channel"] == "shell":
                current_date = datetime.now()
                outputs[msg_id].end_time = current_date.isoformat() + 'Z'
                outputs[msg_id].execution_count = message_data["content"]["execution_count"]


            if "execution_state" in message_data["content"] and \
                    message_data["content"]["execution_state"] == "idle" \
                    and msg_id in outputs:
                outputs[msg_id].completed = True

                # if content is emtpy that means nothing got published
                # so go ahead and publish to the wall
                # if outputs[msg_id].content == []:
                #     channel.basic_publish(
                #         exchange='jupyter',
                #         routing_key=session_id,
                #         body=f"Message {msg_id} just completed. {outputs[msg_id].content}"
                #     )

            if message_data["msg_type"] in ["stream", "display_data", "execute_result", "error"]:
                outputs[msg_id].msg_type = message_data['msg_type']
                ### if stream, then append to existing output if exists
                print("message data is ", message_data)
                # Extract output and append to existing output
                output_data = message_data["content"].get("data")
                if output_data is not None:
                    temp_output = {}
                    for key, val in output_data.items():
                        temp_output[key] = val
                    outputs[msg_id].content.append(temp_output)

                elif 'text' in message_data["content"]:
                    key = message_data["content"]['name']
                    val = message_data["content"]['text']

                    # outputs[msg_id].content.append({key:outputs[msg_id].content.get(key, '') + val})
                    if len(outputs[msg_id].content) > 0 and message_data["msg_type"] == "stream":
                        prev_val = outputs[msg_id].content[-1].get(key)
                        if prev_val is not None:
                            outputs[msg_id].content[-1][key] = prev_val + val
                        else:
                            outputs[msg_id].content.append({key: val})
                    else:
                        outputs[msg_id].content.append({key: val})
                elif "traceback" in message_data["content"]:
                    for key in ["traceback", "ename", "evalue"]:
                        outputs[msg_id].content.append({key:message_data["content"][key]})
                outputs[msg_id].last_update_time = message_data['header']['date']

                # print("Publishing now...")
                # channel.basic_publish(
                #     exchange='jupyter',
                #     routing_key=session_id,
                #     body=f"Message {msg_id}  has an ouput. {outputs[msg_id].content}"
                # )


    return outputs

@app.get("/collection")
async def get_kernel_info_collection():
    kernel_info_array = [kernel.dict() for kernel in kernel_info_collection.values()]
    return kernel_info_array

@app.get("/kernels")
def get_kernels():
    # list the kernels created by the user
    url = urljoin(base_url, "/api/kernels")
    # Get the XSRF token
    session = requests.Session()
    response = session.get(base_url)
    xsrf_token = response.cookies.get('_xsrf')

    print(f"url is {url} and token to use is {token}")

    headers = {
        'Authorization': f'token {token}',
        "X-XSRFToken": xsrf_token,
        "Referer": base_url
    }
    if response.status_code == 201 or response.status_code == 200:
        return response.json()
    else:
        print (response.status_code)
        raise HTTPException(status_code=500, detail=f"Failed to get kernels {response.text}")


@app.get("/kernelspecs")
async def get_kernelspecs():
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
        return response.json()['kernelspecs']
    else:
        raise HTTPException(status_code=500, detail=f"Failed to get kernelspecs {response.text}")

@app.get("/heartbeat")
async def heartbeat():
    return {"status": "ok"}


@app.post("/kernels/")
async def create_kernel(kernel_info: KernelInfo):

    if len(kernel_websockets) == max_number_kernels:
        raise HTTPException(status_code=400,
                            detail=f"Maximum number of kernels reached. Please delete one of the existing kernels.")

    url = urljoin(base_url, "/api/kernels")
    if kernel_info.name is None:
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

    if kernel_info.name not in kernel_specs:
        raise HTTPException(status_code=400, detail=f"Not a valid kernel_name. Valid values are: {list(kernel_specs.keys())}")

    response = requests.post(url, headers=headers, json={"name": kernel_info.name})

    if response.status_code != 201:
        raise HTTPException(status_code=500, detail=f"Failed to create kernel {response.text}")
    elif response.status_code == 201:
        print(f'Successfully created kernel {kernel_info.name}')
        kernel_id = response.json()['id']

        # set the kernel_id field of the kernel_info object with the kernel_id
        kernel_info.kernel_id = kernel_id

        # add the enhanced kernel_info object to the kernel_info_collection dictionary
        kernel_info_collection[kernel_id] = kernel_info

        kernel_websockets[kernel_id] = None
        print(kernel_websockets)
        session_id = str(uuid.uuid4())
        ws_url = urljoin(ws_base_url, f"/api/kernels/{kernel_id}/channels?session_id={session_id}")

        kernel_websockets[kernel_id] = await websockets.connect(ws_url, extra_headers=headers, max_size=5_000_000)
        # asyncio.create_task(check_messages(kernel_websockets[kernel_id], rabbitmq_connection))
        asyncio.create_task(check_messages(kernel_websockets[kernel_id]))

        response_object = response.json()
        response_object.update({"session_id": session_id})
        return response_object
    else:
        raise HTTPException(status_code=500, detail=f"Failed to create kernel {response.text}")

@app.delete("/kernels/{kernel_id}")
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
            del kernel_info_collection[kernel_id]
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
    outputs[msg_id] = {}
    return {"msg_id": msg_id}

@app.post("/stop/{kernel_id}")
async def stop_kernel(kernel_id: str):
    print(f"Stopping kernel {kernel_id}")
    if kernel_id not in kernel_websockets:
        raise HTTPException(status_code=400, detail="Kernel not started")
    ws = kernel_websockets[kernel_id]
    await ws.close()
    del kernel_websockets[kernel_id]

# Restart kernel
@app.post("/restart/{kernel_id}")
async def restart_kernel(kernel_id: str):
    if kernel_id not in kernel_info_collection:
        raise HTTPException(status_code=400, detail="Kernel not started")
    url = urljoin(base_url, f"/api/kernels/{kernel_id}/restart")
    # Get the XSRF token
    session = requests.Session()
    response = session.get(base_url)
    xsrf_token = response.cookies.get('_xsrf')
    headers = {
        'Authorization': f'token {token}',
        "X-XSRFToken": xsrf_token,
        "Referer": base_url
    }
    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        print(f"Successfully restarted kernel {kernel_id}")
        return {"status": "ok"}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to restart kernel {response.text}")


@app.get("/status/{msg_id}")
async def check_status(msg_id: str):
    # Getting message from users.
    if msg_id not in outputs:
        raise HTTPException(status_code=400, detail="Invalid msg_id")
    else:
        if outputs[msg_id] is not None:
            # print(f"Output for {msg_id} is {outputs[msg_id]}")
            print(f"{msg_id} has output and is of type {type(outputs[msg_id])}")
        else:
            print(f"No output yet for {msg_id}")
    return outputs[msg_id]

@app.get("/status/{msg_id}/stream")
async def check_status_stream(request: Request, msg_id: str):
    headers = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*'
    }

    async def event_generator():
        last_msg_update = None

        if msg_id not in outputs:
            print("msg_id not found in outputs")
            raise HTTPException(status_code=500, detail=f"{msg_id} not found in outputs")
            # TODO: should we return an empty object here? or return 404?

        while True:

            # if the object is empty then print the message to the stdout and skip it

            if await request.is_disconnected():
                print("request disconnected")
                break

            # Checks for new messages and return them to client if any
            if last_msg_update is None or last_msg_update != outputs[msg_id].last_update_time:
                # if not isinstance(outputs[msg_id], ExecOutput):
                if outputs[msg_id] == {}:
                    message = {
                        "event": "new_message",
                        "id": "message_id",
                        "data": ""

                    }
                    yield json.dumps(message)
                else:
                    data = outputs[msg_id].json()  # should return a JSON string
                    message = {
                        "event": "new_message",
                        "id": "message_id",
                        "data": data

                    }
                    yield message

                    last_msg_update = outputs[msg_id].last_update_time

            if outputs[msg_id] != {} and outputs[msg_id].completed is True:
                if last_msg_update != outputs[msg_id].last_update_time:
                    data = outputs[msg_id].json()
                    message = {
                        "event": "new_message",
                        "id": "message_id",
                        "data": data,
                        "retry": RETRY_TIMEOUT

                    }
                    yield message

                break

            await asyncio.sleep(STREAM_DELAY)

    return EventSourceResponse(event_generator(), headers=headers)


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
