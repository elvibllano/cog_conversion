import sys
import json
import os
from conversione import run

def handler(event, context):
    run(event["url"])
    return{
        'StatusCode': 200,
        'body': json.dumps("Conversione cog avvenuta")
    }
