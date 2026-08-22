import boto3
from botocore.client import Config

def build_boto3_client(
    region: str,
    endpoint_url: str | None,
    access_key_id: str | None,
    secret_access_key: str | None,
    path_style: bool,
):
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(s3={"addressing_style": "path" if path_style else "auto"}),
    )

def build_storage_options(
    region: str,
    endpoint_url: str | None,
    access_key_id: str | None,
    secret_access_key: str | None,
    allow_http: bool,
    path_style: bool,
) -> dict[str, str]:
    options: dict[str, str] = {"aws_region": region}
    if endpoint_url:
        options["aws_endpoint_url"] = endpoint_url
    if access_key_id:
        options["aws_access_key_id"] = access_key_id
    if secret_access_key:
        options["aws_secret_access_key"] = secret_access_key
    if allow_http:
        options["aws_allow_http"] = "true"
    if path_style:
        options["aws_virtual_hosted_style_request"] = "false"
    return options