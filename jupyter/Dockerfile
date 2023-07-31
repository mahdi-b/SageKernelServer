# Use the official Jupyter notebook Python 3.9 image
FROM jupyter/base-notebook:python-3.9.7

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Set the Jupyter Notebook token
ENV JUPYTER_TOKEN=123456

# Start Jupyter Notebook
CMD ["start-notebook.sh", "--ServerApp.token=123456", "--no-browser", "--ServerApp.ip=0.0.0.0"]
