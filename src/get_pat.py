# Get personal access token by first retrieving AAD token via ADAL
# then use it to retrieve a pat (cli
# may not support aad token so a pat is required)

# from adal import AuthenticationContext
# from selenium import webdriver
# from urllib.parse import urlparse, parse_qs
# from requests.exceptions import HTTPError
# import time, uuid, requests, json, logging

from msrestazure.azure_active_directory import AADTokenCredentials
from requests.exceptions import HTTPError
import json,adal,requests
import logging


log = logging.getLogger()

AUTHORITY_HOST_URL = 'https://login.microsoftonline.com/'
DATABRICKS_RESOURCE_ID = '2ff814a6-3304-4ab8-85cb-cd0e6f879c1d'

# TEMPLATE_AUTHZ_URL = ('https://login.windows.net/{}/oauth2/authorize?' +
# 		 'response_type=code&client_id={}&redirect_uri={}&' +
# 		 'state={}&resource={}')

DB_RESOURCE_ID = '/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Databricks/workspaces/{}'

LIST_NODE_TYPES_ENDPOINT = '/api/2.0/clusters/list-node-types'
CREATE_TOKEN_ENDPOINT = '/api/2.0/token/create'
REDIRECT_URI = 'http://localhost'



def get_adb_authentication_client_key(params):
	"""
    Authenticate using service principal w/ key.
    """
	authority_host_uri = 'https://login.microsoftonline.com'
	tenant = params['tenant_id']
	authority_uri = authority_host_uri + '/' + tenant
	resource_uri = params['databricks_resource_id']
	client_id = params['client_id']
	client_secret = params['client_secret']
	context = adal.AuthenticationContext(authority_uri, api_version=None)
	mgmt_token = context.acquire_token_with_client_credentials(resource_uri, client_id, client_secret)
	credentials = AADTokenCredentials(mgmt_token, client_id)
	log.info("created aad authentication token")
	return credentials


'''
The management token is used for the admin login flows (users/service principal with Contributor access)
- If the user/sp does not exist in the workspace, they will be automatically created as an admin user
Using the bearer token (AAD access token) we cannot query the role or permission of the user/sp in the Azure Databricks Resource, 
but using the management token we are able to query AAD for the role of the user/sp
'''


def get_adb_authorization_client_key(params):
	"""
    Authenticate using service principal w/ key.
    """
	authority_host_uri = 'https://login.microsoftonline.com'
	tenant = params['tenant_id']
	authority_uri = authority_host_uri + '/' + tenant
	resource_uri = 'https://management.core.windows.net/'
	client_id = params['client_id']
	client_secret = params['client_secret']
	context = adal.AuthenticationContext(authority_uri, api_version=None)
	mgmt_token = context.acquire_token_with_client_credentials(resource_uri, client_id, client_secret)
	credentials = AADTokenCredentials(mgmt_token, client_id)
	log.info("created management authorization token for databricks resource")
	return credentials


'''
invoke databricks REST api, in this case "list node types" which is one of the simplest and retruns available azure vm types in a workspace and 
while doing so we initalize databricks workspace
'''

def initialize_databricks_workspace(aad_token, mgmt_token,params):
	location = params['location']
	db_host = 'https://'+location+'.azuredatabricks.net'
	subscription_id = params['subscription_id']
	rg_name = params['rg_name']
	workspace_name = params['workspace_name']
	log.debug('aad: {}'.format(aad_token))
	log.debug('mgmt: {}'.format(mgmt_token))

	uri = db_host + LIST_NODE_TYPES_ENDPOINT
	db_resource_id = DB_RESOURCE_ID.format(subscription_id, rg_name, workspace_name)
	log.info('Using Databricks resource id: '.format(db_resource_id))
	log.info('Using host: {}'.format(uri))
	headers = {
		'Authorization': 'Bearer ' + aad_token,
		'X-Databricks-Azure-Workspace-Resource-Id': db_resource_id,
		'X-Databricks-Azure-SP-Management-Token': mgmt_token
	}

	res = requests.get(uri, headers=headers)

	try:
		res.raise_for_status()
		print("\n\nSuccessfully initialized databricks workspace \n\nList available node types: ", res.content, '\n\n')
	except HTTPError:
		print('Failed to initialize databricks workspace - Reason: \n\n', res.content, '\n\n')
		return


def pat_from_aad_token(aad_token,mgmt_token,params):
	location = params['location']
	db_host = 'https://'+location+'.azuredatabricks.net'
	subscription_id = params['subscription_id']
	rg_name = params['rg_name']
	workspace_name = params['workspace_name']
	log.debug('aad: {}'.format(aad_token))
	log.debug('mgmt: {}'.format(mgmt_token))

	uri = db_host + CREATE_TOKEN_ENDPOINT
	db_resource_id = DB_RESOURCE_ID.format(subscription_id, rg_name, workspace_name)
	log.info('Using Databricks resource id: '.format(db_resource_id))
	log.info('Using host: {}'.format(uri))
	headers = {
		'Authorization': 'Bearer ' + aad_token,
		'X-Databricks-Azure-Workspace-Resource-Id': db_resource_id,
		'X-Databricks-Azure-SP-Management-Token': mgmt_token
	}

	log.info("Exchanging AAD token for PAT for further provisioning")
	res = requests.post(uri, headers=headers)

	try:
		res.raise_for_status()
	except HTTPError:
		print('Failed to generate databricks platform access token - Reason: \n\n', res.content, '\n\n')
		return

	log.debug('Full response from PAT request: {}'.format(res))
 	log.debug('Content: {}'.format(res.content))
 	return json.loads(res.content)['token_value']


def run(params):
	log.info('generating AAD authentication token')
	aad_token = get_adb_authentication_client_key(params).token['access_token']
	log.info('generating AAD management authorization token')
	mgmt_token = get_adb_authorization_client_key(params).token['access_token']
	log.info('AAD Management Token: '.format(mgmt_token))
	initialize_databricks_workspace(aad_token, mgmt_token, params)
	log.info('Initializing databricks workspace')
	# Exchange AAD token for PAT (for use with CLI lib) via Token API
	pat = pat_from_aad_token(aad_token, params['db_host'], params['subscription_id'], params['rg_name'],
							 params['workspace_name'])
	log.info('Exchanged for PAT: '.format(pat))
	return pat



#
# generate AAD token using interactive mode
#
#
# def get_authorization_code(tenant_id, client_id, redirect_uri, authorization_url, auth_state):
# 	# open browser
# 	dr = webdriver.Chrome()
# 	# load user login page
# 	dr.get(authorization_url)
# 	# wait until the user login or kill the process
# 	code_received = False
# 	code = ''
#
# 	while not code_received:
# 		cur_url = dr.current_url
# 		if cur_url.startswith(redirect_uri):
# 			parsed = urlparse(cur_url)
# 			query = parse_qs(parsed.query)
# 			code = query['code'][0]
# 			state = query['state'][0]
# 			# throw exception if the state does not match
# 			if state != str(auth_state):
# 				raise ValueError('state does not match')
# 			code_received = True
# 			dr.close()
#
# 	if not code_received:
# 		log.error('Error in requesting auth code for AAD token')
# 		dr.close()
# 	# auth code is returned. If not success then empty code returned
# 	return code
#
# def get_refresh_and_aad_token(tenant_id, client_id, client_secret, redirect_uri):
# 	# build URL for auth code
# 	auth_state = uuid.uuid4() # - used for preventing CSRF attacks
# 	authorization_url = TEMPLATE_AUTHZ_URL.format(
# 		tenant_id,
# 		client_id,
# 		redirect_uri,
# 		auth_state,
# 		DATABRICKS_RESOURCE_ID
# 	)
#
# 	# configure AuthenticationContext (reference link)
# 	# authority URL and tenant ID are used
# 	authority_url = AUTHORITY_HOST_URL + tenant_id
# 	context = AuthenticationContext(authority_url)
#
# 	# Obtain the authorization code in by a HTTP request in the browser
# 	# then copy it here
# 	# Or, call the function above to get the authorization code
# 	authz_code = get_authorization_code(tenant_id, client_id, redirect_uri, authorization_url, auth_state)
#
# 	# API call to get the token, the response is a key-value dict
# 	token_response = context.acquire_token_with_authorization_code(
# 		authz_code,
# 		redirect_uri,
# 		DATABRICKS_RESOURCE_ID,
# 		client_id,
# 		client_secret)
#
# 	# you can print all the fields in the token_response
# 	for key in token_response.keys():
# 		log.debug(str(key) + ': ' + str(token_response[key]))
#
# 	# the tokens can be returned as a pair (or you can return the full
# 	# token_response)
# 	return (token_response['refreshToken'], token_response['accessToken'])
#
# # Use Token API to exhange AAD token for PAT
# def pat_from_aad_token(aad_token, db_host, subscription_id, rg_name, ws_name):
# 	log.debug('aad: {}'.format(aad_token))
#
# 	uri = db_host + CREATE_TOKEN_ENDPOINT
# 	db_resource_id = DB_RESOURCE_ID.format(subscription_id, rg_name, ws_name)
# 	log.info('Using Databricks resource id: '.format(db_resource_id))
# 	log.info('Using host: {}'.format(uri))
# 	headers = {
# 		'Authorization': 'Bearer ' + aad_token,
# 		'X-Databricks-Azure-Workspace-Resource-Id': db_resource_id
# 	}
#
# 	# First one is just a "wake up call" (to launch the workspace) - note this can be any request, not necessarily
# 	# a PAT request, but we are keeping it the same for simplicity
# 	log.info('Sending initial dummy API call to launch workspace')
# 	requests.post(uri, headers=headers)
# 	log.info("Dummy API to launch workspace complete. Now exchanging AAD token for PAT for further provisioning")
# 	res = requests.post(uri, headers=headers)
#
# 	try:
# 		res.raise_for_status()
# 	except HTTPError:
# 		print('Failed to convert AAD token to PAT - Reason: \n\n', res.content, '\n\n')
# 		return
#
# 	log.debug('Full response from PAT request: {}'.format(res))
# 	log.debug('Content: {}'.format(res.content))
# 	return json.loads(res.content)['token_value']
#
# def run(params):
# 	# Obtain AAD token via ADAL:
# 	redirect_uri = REDIRECT_URI
# 	log.info('Retrieving AAD token, redirect URI: '.format(redirect_uri))
#
# 	(refresh_token, aad_token) = get_refresh_and_aad_token(params['tenant_id'], params['client_id'],
# 														   params['client_secret'], redirect_uri)
#
# 	log.info('AAD Token: '.format(aad_token))
# 	log.debug('Refresh token: '.format(refresh_token))
#
# 	# Exchange AAD token for PAT (for use with CLI lib) via Token API
# 	pat = pat_from_aad_token(aad_token, params['db_host'], params['subscription_id'], params['rg_name'],
# 							 params['workspace_name'])
# 	log.info('Exchanged for PAT: '.format(pat))
# 	return pat