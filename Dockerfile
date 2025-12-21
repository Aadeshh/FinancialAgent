FROM public.ecr.aws/lambda/python:3.12

RUN dnf update -y && \
    dnf install -y gcc gcc-c++ python3-devel && \
    dnf clean all

COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ${LAMBDA_TASK_ROOT}
COPY .env ${LAMBDA_TASK_ROOT}

CMD [ "main.lambda_handler" ]