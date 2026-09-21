try:
    from simple_salesforce import Salesforce
except Exception:  # pragma: no cover
    Salesforce = None

def get_salesforce(username: str, password: str, security_token: str):
    if Salesforce is None:
        raise RuntimeError("simple-salesforce is not installed. `pip install simple-salesforce`")
    return Salesforce(username=username, password=password, security_token=security_token)
