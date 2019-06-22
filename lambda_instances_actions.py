#!/usr/bin/python

import boto3
import logging
import base64
import json
import os
import settings

Logger = None
ValidActions = ["Start", "Stop", "Update", "Presign", "Delete"]

DDBTableName = settings.DDBTableName

def ParseJWT(Token):
    global Logger
    
    Auth = Token.split(".")[1]
    
    MissingPadding = len(Auth)%4
    if MissingPadding != 0: Auth += "="*(4-MissingPadding)
        
    try:
        AuthDict = json.loads(base64.urlsafe_b64decode(Auth))
    except Exception as e:
        Logger.error("Could not parse JWT: "+str(e)+" "+Token)
        AuthDict = {}

    return(AuthDict)

# This Lambda is getting the request to perform an action on the instance
def lambda_handler(event, context):
    global Logger,ValidActions,DDBTableName
    
    logging.basicConfig()
    Logger = logging.getLogger()
    Logger.setLevel(logging.INFO)

    if os.environ.get("DynamoDBTableName") is not None: DDBTableName = os.environ.get("DynamoDBTableName")

    Response               = {}
    Response["statusCode"] = 200
    Response["headers"]    = {"Access-Control-Allow-Origin": "*"}
    Response["body"]       = ""

    # if "headers" not in event:
    #     Logger.error("No headers supplied: "+str(event))
    #     Response["body"] = '{"Error":"No headers supplied."}'
    #     return(Response)
        
    # if "Authorization" not in event["headers"]:
    #     Logger.error("No Authorization header supplied: "+str(event))
    #     Response["body"] = '{"Error":"No authorization header supplied."}'
    #     return(Response)
        
    # AuthInfo = ParseJWT(event["headers"]["Authorization"])
    # if "identities" not in AuthInfo:
    #     Logger.error("No identity information in JWT")
    #     Response["body"] = '{"Error":"No identity information in authorization."}'
    #     return(Response)
        
    # Username = AuthInfo["identities"][0]["userId"].split("\\")[1] # Username is expected to be "DOMAIN\\username"
    # ADGroups = AuthInfo["custom:ADGroups"]

    if "queryStringParameters" not in event:
        Logger.error("Did not find queryStringParameters")
        Response["body"] = '{"Error":"No query string in request."}'
        return(Response)

    if "InstanceId" not in event["queryStringParameters"]:
        Logger.error("No instance id specified")
        Response["body"] = '{"Error":"No instance id specified in request."}'
        return(Response)

    if "Action" not in event["queryStringParameters"]:
        Logger.error("No action specified")
        Response["body"] = '{"Error":"No action specified in request."}'
        return(Response)
        
    InstanceId = event["queryStringParameters"]["InstanceId"]
    Action     = event["queryStringParameters"]["Action"]
    
    if Action not in ValidActions:
        Logger.error("Invalid specified: "+Action)
        Response["body"] = '{"Error":"Invalid action specified in request."}'
        return(Response)

    DynamoDB = boto3.client("dynamodb")
 
    try:
        InstanceInfo = DynamoDB.get_item(TableName=DDBTableName,
                                          Key={"InstanceId":{"S":InstanceId}})
    except Exception as e:
        Logger.error("DynamoDB error: "+str(e))
        Response["body"] = '{"Error":"Database query error."}'
        return(Response)

    if "Item" not in InstanceInfo:
        Logger.error("Instance not found in DDB: "+InstanceId)
        Response["body"] = '{"Error":"Instance not found in database."}'
        return(Response)

    try:
        OwnedBy = InstanceInfo["Item"]["UserName"]["S"]
    except:
        Logger.error("Username of instance owner not found in data: "+str(InstanceInfo))
        Response["body"] = '{"Error":"Instance owner not found."}'
        return(Response)
    
    State = InstanceInfo["Item"]["InstanceState"]["S"]

    if Action == "Start" and State != "Stopped":
        Logger.error("Cannot start - state is not Stopped: "+State)
        Response["body"] = '{"Warning":"You cannot start an Instance that is not in a Stopped state."}'
        return(Response)
        
    if Action == "Stop" and State not in {"InService"}:
        Logger.error("Cannot stop - state is not InService: "+State)
        Response["body"] = '{"Warning":"You cannot stop an Instance that is not in an InService state."}'
        return(Response)

    sagemaker_client = boto3.client("sagemaker", region_name=InstanceInfo["Item"]["Region"]["S"])
    NextState  = ""
    
    if Action == "Start":
        try:
            sagemaker_client.start_notebook_instance(NotebookInstanceName=InstanceId)
            NextState = "InService"
        except Exception as e:
            Logger.error("SageMaker API error on start: "+str(e))
            Response["body"] = '{"Error":"SageMaker API query error for start."}'
            return(Response)

    if Action == "Stop":
        try:
            sagemaker_client.stop_notebook_instance(NotebookInstanceName=InstanceId)
            NextState = "Stopped"
        except Exception as e:
            Logger.error("SageMaker API error on stop: "+str(e))
            Response["body"] = '{"Error":"SageMaker API query error for stop."}'
            return(Response)

    Response["body"] = '{"Success":"SageMaker '+Action+' in progress for '+InstanceId+'."}'

    try:
        DynamoDB.update_item(TableName=DDBTableName,
                                Key={settings.instanceIdKey:{"S":InstanceId}},
                                UpdateExpression="set InstanceState = :s",
                                ExpressionAttributeValues={":s":{"S":NextState}})
    except Exception as e:
        Logger.error("Could not update DynamoDB for instance "+InstanceId+": "+str(e))

    return(Response)


def test_lambda_handler():
    event = {
        "headers" : {
            "Authorization" : "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        },
        "queryStringParameters" : {
            "InstanceId" : "fastai-with-efs",
            "Action" : "Start"

        }

    }

    lambda_handler(event,"")