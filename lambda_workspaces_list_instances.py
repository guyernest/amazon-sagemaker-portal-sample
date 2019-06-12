#!/usr/bin/python

#
# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import boto3
from boto3.dynamodb.conditions import Attr
import os
import logging
import json
import base64

Logger       = None
DDBTableName = "SagemakerPortal"

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

def lambda_handler(event, context):
    global Logger,DDBTableName
    
    logging.basicConfig()
    Logger = logging.getLogger()
    Logger.setLevel(logging.INFO)

    if os.environ.get("DynamoDBTableName") is not None: DDBTableName = os.environ.get("DynamoDBTableName")

    Response               = {}
    Response["statusCode"] = 200
    Response["headers"]    = {"Access-Control-Allow-Origin": "*"}
    Response["body"]       = ""

    if "headers" not in event:
        Logger.error("No headers supplied: "+str(event))
        Response["body"] = '{"Error":"No headers supplied."}'
        return(Response)
        
    if "Authorization" not in event["headers"]:
        Logger.error("No Authorization header supplied: "+str(event))
        Response["body"] = '{"Error":"No authorization header supplied."}'
        return(Response)
        
    AuthInfo = ParseJWT(event["headers"]["Authorization"])
    if "identities" not in AuthInfo:
        Logger.error("No identity information in JWT")
        Response["body"] = '{"Error":"No identity information in authorization."}'
        return(Response)
        
    Username = AuthInfo["identities"][0]["userId"].split("\\")[1] # Username is expected to be "DOMAIN\\username"
    ADGroups = AuthInfo["custom:ADGroups"]
    
    ListAll = False
    try:
        if "queryStringParameters" in event:
            if "ListAll" in event["queryStringParameters"]:
                if ADGroups.find("AdminGroupMember") >= 0:
                    ListAll = True
    except:
        pass
            
    Logger.info("Username: "+Username+" ADGroups: "+ADGroups+ " ListAll: "+str(ListAll))

    Table = boto3.resource("dynamodb").Table(DDBTableName)
    Expression = Attr("UserName").eq(Username)
    
    StartKey       = {}
    InstancesList = []
    while True: # Loop until no more items come from the DDB Scan
        Logger.info("DDB scan loop, StartKey="+str(StartKey))
        try:
            if len(StartKey) == 0:  
                if ListAll:
                    Result = Table.scan()
                else:
                    Result = Table.scan(FilterExpression=Expression)
            else:
                if ListAll:
                    Result = Table.scan(ExclusiveStartKey=StartKey)
                else:
                    Result = Table.scan(FilterExpression=Expression, ExclusiveStartKey=StartKey)
        except Exception as e:
            Logger.error("DynamoDB error: "+str(e))
            Response["body"] = '{"Error":"DynamoDB scan error."}'
            return(Response)

        for Instance in Result["Items"]:
            Logger.info("Processing "+Instance["InstanceId"])
            
            # Need to convert Decimal() to actual numbers before returning JSON
            if "LastConnected" in Instance: Instance["LastConnected"] = int(Instance["LastConnected"])
            if "LastTouched"   in Instance: Instance["LastTouched"]   = int(Instance["LastTouched"])

            InstancesList.append(Instance)

    JSONObject = {"Instances":InstancesList}
    Response["body"] = json.dumps(JSONObject)

    return(Response)
