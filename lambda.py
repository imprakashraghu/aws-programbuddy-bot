import json
import boto3
import os
from boto3.dynamodb.conditions import Key
from io import BytesIO
import zipfile
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
s3 = boto3.resource("s3")
ses = boto3.client("ses")

def sendEmail(project_information, url):
    try:
        senderEmail = 'Program Buddy Bot <prakashjaw05+program-buddy@gmail.com>'
        toEmail = project_information['email']
        subject = f"Exported Successfully - Project {project_information['project_name']} from Program Buddy"
        htmlBody = f"""
<html>
<head></head>
<body>
<h1>Hey {project_information['name']},</h1>
<p>The following url contains the exported project built using Program Buddy Bot.<br/>
    <a target='_blank' href='{url}'>Download Project</a>.</p><br/>
<p><small><i>Program Buddy Team</i></small></p>
</body>
</html>
        """
        response = ses.send_email(
            Destination={
                'ToAddresses': [
                    toEmail,
                ],
            },
            Message={
                'Body': {
                    'Html': {
        
                        'Data': htmlBody
                    },
                },
                'Subject': {

                    'Data': subject
                },
            },
            Source=senderEmail
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])
        
def createZipFileStream(bucketName, bucketFilePath, jobKey, createUrl=False):
    response = {} 
    bucket = s3.Bucket(bucketName)
    filesCollection = bucket.objects.filter(Prefix=bucketFilePath).all() 
    archive = BytesIO()

    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zip_archive:
        for file in filesCollection:
            with zip_archive.open(file.key, 'w') as file1:
                file1.write(file.get()['Body'].read())  

    archive.seek(0)
    s3.Object(bucketName, bucketFilePath + '/' + jobKey + '.zip').upload_fileobj(archive)
    archive.close()

    if createUrl is True:
        s3Client = boto3.client('s3')
        response = s3Client.generate_presigned_url('get_object', Params={'Bucket': bucketName,
                                                                                    'Key': '' + bucketFilePath + '/' + jobKey + '.zip'},
                                                              ExpiresIn=3600)

    return response

def buildPackageFile(project_information):
    # creating package.json
    packagePayload = {
         "name": project_information['project_name'],
          "version": "1.0.0",
          "description": "created with the help of program-buddy",
          "main": "app.js",
          "scripts": {
            "test": "echo \"Error: no test specified\" && exit 1",
            "start": "node app.js"
          },
          "author": project_information['name'],
          "license": "ISC",
          "dependencies": {
            "dotenv": "^16.0.1",
            "express": "^4.18.1",
            "mongoose": "^6.3.5"
          }
    }
    resultContent = json.dumps(packagePayload, sort_keys=True, indent=2, separators=(',', ': '))
    # writing to file
    encoded_string = resultContent.encode("utf-8")
    bucket_name = "program-buddy"
    file_name = "package.json"
    s3_path = project_information['name'] + "/" + project_information['sessionId']  + "/" + project_information['project_name'] + "/" + file_name
    # saving file into s3
    s3.Bucket(bucket_name).put_object(Key=s3_path, Body=encoded_string)

def createRequiredFiles(project_information):
    # creating config file
    configContent = """
'use strict'
require('dotenv').config()

module.exports = {
    DATABASE_URL: process.env.DB_URL,
    PORT: process.env.PORT
}
    """
    encodedConfigString = configContent.encode("utf-8")
    bucket_name = "program-buddy"
    file_name = "index.js"
    s3_path = project_information['name']+ "/" + project_information['sessionId'] + "/" + project_information['project_name'] + "/config/" + file_name
    # saving config file into s3
    s3.Bucket(bucket_name).put_object(Key=s3_path, Body=encodedConfigString)
    # creating the database file
    dbContent = """
const mongoose = require('mongoose')
const {DATABASE_URL} = require('../config')

mongoose
  .connect(DATABASE_URL, { useNewUrlParser: true, socketTimeoutMS: 30000, keepAlive: true })
  .then(() => console.log('Database Connected'))
  .catch((error) => console.log(error))

module.exports = mongoose
    """
    encodedDBString = dbContent.encode("utf-8")
    bucket_name = "program-buddy"
    file_name = "index.js"
    s3_path = project_information['name']+ "/" + project_information['sessionId'] + "/" + project_information['project_name'] + "/db/" + file_name
    # saving database file into s3
    s3.Bucket(bucket_name).put_object(Key=s3_path, Body=encodedDBString)

def buildModelSchemaFileContent(model):
    modelProperties = {}
    for item in model['properties']:
        modelProperties[item] = {
            'type': 'String'
        }
    result = "const mongoose = require('mongoose')\nconst "+model['model_name']+"Schema = new mongoose.Schema("+json.dumps(modelProperties, sort_keys=True, indent=2, separators=(',', ': '))+",{timestamps: true,})\nmodule.exports = mongoose.model('"+ model['model_name'] +"', "+model['model_name']+"Schema)"
    resultEncodedString = result.encode("utf-8")
    return resultEncodedString

def buildIndexRouteFileContent(model):
    resultContent = f"""
'use strict'
const router = require('express').Router()
const {model['model_name']}Model = require('./model')

// READ ALL USER
router.get('/', async (req, res) => {{
    try {{
         
        const users = await userModel.find({{}},{{__v: 0}})
        res.status(200).send(users)

    }} catch (err) {{
        res.status(500).json({{status: false, message: 'Internal Server Error', error: err.message || null}})
    }}
}})
// CREATE USER
router.post('/', async (req, res) => {{
    try {{

        // EVERYTHING CANNOT BE NULL
        if ({" || ".join(["!req.body."+item for item in model['properties']])}) {{
            return res.status(400).json({{status: false, message: 'Parameters Missing!'}})
        }}

        const {model['model_name']}CreationPayload = {{
            {f",{os.linesep}".join([item+": req.body."+item for item in model['properties']])}
        }}

        const {model['model_name']} = new {model['model_name']}Model({model['model_name']}CreationPayload)
        {model['model_name']}.save((err, doc) => {{
            if (err) {{
                res.status(500).json({{status: false, message: 'Internal Server Error', error: err.message || null}})
            }}
            res.status(200).json({{status: true, message: "{model['model_name']} Created Successfully", data: doc}})
        }})

    }} catch (err) {{
        res.status(500).json({{status: false, message: 'Internal Server Error', error: err.message || null}})
    }}
}})
// UPDATE USER
router.put('/:id', async (req, res) => {{
    try {{
        // EVERYTHING CANNOT BE NULL
        if ({" || ".join(["!req.body."+item for item in model['properties']])}) {{
            return res.status(400).json({{status: false, message: 'Parameters Missing!'}})
        }}

        let {model['model_name']}UpdatePayload = {{
            {f",{os.linesep}".join([item+": req.body."+item for item in model['properties']])}
        }}

        await {model['model_name']}Model.findByIdAndUpdate(req.params.id, {{
            $set: {model['model_name']}UpdatePayload,
        }})

        res.status(200).json({{status: true, message: '{model['model_name']} Updated Successfully'}})

    }} catch (err) {{
        res.status(500).json({{status: false, message: 'Internal Server Error', error: err.message || null}})
    }}
}})
// DELETE USER
router.delete('/:id', async (req, res) => {{
    try {{

        await {model['model_name']}Model.findByIdAndDelete(req.params.id)

        res.status(200).json({{status: true, message: '{model['model_name']} Deleted Successfully'}})
        
    }} catch (err) {{
        res.status(500).json({{status: false, message: 'Internal Server Error', error: err.message || null}})
    }}
}})

module.exports = router
    """
    resultEncodedString = resultContent.encode("utf-8")
    return resultEncodedString

def createRouterFiles(project_information, model_information):
    for model in model_information:
        # create model.js file
        encoded_string = buildModelSchemaFileContent(model)
        bucket_name = "program-buddy"
        file_name = "model.js"
        s3_path = project_information['name']+ "/" + project_information['sessionId'] + "/" + project_information['project_name'] + "/routes/" + model['model_name'] + "/" + file_name
        # saving file into s3
        s3.Bucket(bucket_name).put_object(Key=s3_path, Body=encoded_string)
        # create index.js file
        encoded_string_index = buildIndexRouteFileContent(model)
        bucket_name = "program-buddy"
        file_name = "index.js"
        s3_path = project_information['name']+ "/" + project_information['sessionId'] + "/" + project_information['project_name'] + "/routes/" + model['model_name'] + "/" + file_name
        # saving file into s3
        s3.Bucket(bucket_name).put_object(Key=s3_path, Body=encoded_string_index)
    
def createMainFile(project_information, model_information):
    result = f"""
require('./db')
const express = require('express')
const app = express()

app.use(express.urlencoded({{extended: true}}))
app.use(express.json())

const {{PORT}} = require('./config')

{f"{os.linesep}".join("const "+item['model_name']+" = require('./routes/"+item['model_name']+"')" for item in model_information)}

{f"{os.linesep}".join("app.use('/api/v1/"+item['model_name']+"',"+item['model_name']+")" for item in model_information)}

app.listen(PORT, () => console.log('Api Server is Running!'))
    """
    resultEncodedString = result.encode("utf-8")
    bucket_name = "program-buddy"
    file_name = "app.js"
    s3_path = project_information['name']+ "/" + project_information['sessionId'] + "/" + project_information['project_name'] + "/" + file_name
    # saving file into s3
    s3.Bucket(bucket_name).put_object(Key=s3_path, Body=resultEncodedString)
    
def get_slots(intent_request):
    return intent_request['sessionState']['intent']['slots']
    
def get_slot(intent_request, slotName):
    slots = get_slots(intent_request)
    if slots is not None and slotName in slots and slots[slotName] is not None:
        return slots[slotName]['value']['interpretedValue']
    else:
        return None

def lambda_handler(event, context):
    intent_name = event['sessionState']['intent']['name']
    projectTable = dynamodb.Table("ProjectInformation")
    schemaTable = dynamodb.Table("SchemaInformation")
    if intent_name == 'ProjectCreation':
        payload = {
            "sessionId": event["sessionId"],
            "name": get_slot(event, 'Name'),
            "email": get_slot(event, 'EmailAddress'),
            "project_name": get_slot(event, 'ProjectName'),
            "framework": get_slot(event, 'Framework')
        }
        # # save to db
        projectTable.put_item(Item=payload)
    if intent_name == 'CapturingModel':
        properties = get_slot(event, 'ModelProperties')
        name = get_slot(event, 'ModelName')
        if properties is not None:
            props_array = properties.split(',')
            sessionUser = projectTable.get_item(Key={'sessionId':event['sessionId']})
            # save to db
            schemaTable.put_item(Item={
                'sessionId':event['sessionId'],
                'model_name':name,
                'properties':props_array,
                'username':sessionUser['Item']['name']
            })
    if intent_name == 'ExportProject':
        sessionId = event['sessionId']
        projectInformation = projectTable.get_item(Key={'sessionId':sessionId})
        models = schemaTable.scan(
            FilterExpression='sessionId = :sId',
            ExpressionAttributeValues={":sId": sessionId}
        )
        # creating package json file
        buildPackageFile(projectInformation['Item'])
        # creating db and configuration files and folders
        createRequiredFiles(projectInformation['Item'])
        # creating router files
        createRouterFiles(projectInformation['Item'], models['Items'])
        # creating app.js file
        createMainFile(projectInformation['Item'], models['Items'])
        # zip the files and folder
        url = createZipFileStream('program-buddy', projectInformation['Item']['name']+"/"+projectInformation["Item"]['sessionId'], projectInformation['Item']['project_name'], True)
        sendEmail(projectInformation['Item'], url)