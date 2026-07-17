# workspace-testing

## Running the FastAPI Server

To run the FastAPI server, navigate to the project directory and execute the following command:

```
uvicorn server:app --reload
```

This command will start the FastAPI server, making it accessible on `http://127.0.0.1:8000`. The `--reload` flag enables automatic reloading of the server for development purposes.

## Supported Model Types

The server supports loading and predicting with models of the following types:

- Scikit-learn (`.pkl`)
- XGBoost (`.json`)
- PyTorch (`.pth`)

To add a new model to the server, place the model file in the `model` directory and ensure it is one of the supported types. The server dynamically loads the model based on the file extension or model type specified in the request.

## Health Check

To verify that the server is running and accessible, you can use the `/ping` endpoint:

```
http://127.0.0.1:8000/ping
```

This endpoint returns a simple `pong` message, indicating that the server is healthy and ready to process requests.

## Creating a Python Virtual Environment

To create a Python virtual environment, navigate to the project directory and execute the following command:

```
python -m venv venv
```

To activate the virtual environment on Windows, run:

```
.\venv\Scripts\activate
```

On Unix or MacOS, use:

```
source venv/bin/activate
```

This will activate the virtual environment, allowing you to install and use the required dependencies in an isolated environment.

## Testing the Dummy Model

To run tests for the dummy model using `pytest`, first ensure that `pytest` is installed by running:

```
pip install pytest
```

Then, navigate to the project directory and execute the following command:

```
pytest test/test_server.py
```

This command will run the tests defined in `test_server.py`, testing the dummy model with both numeric and string inputs to ensure it behaves as expected.
