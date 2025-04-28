import requests
import json
import time
import os
import re
from datetime import datetime, timedelta
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class WikiRequests:
    def __init__(self, api_url):
        self.api_url = api_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'WikiSync/1.0 (Python)'
        })
        self.session.verify = False
        self.logged_in = False
        self.tokens = {}

    def login(self, username, password):
        if self.logged_in:
            return True

        login_token_params = {
            'action': 'query',
            'meta': 'tokens',
            'type': 'login',
            'format': 'json'
        }

        try:
            token_response = self.session.get(self.api_url, params=login_token_params)
            token_response.raise_for_status()
            data = token_response.json()
            login_token = data['query']['tokens']['logintoken']

            login_params = {
                'action': 'login',
                'lgname': username,
                'lgpassword': password,
                'lgtoken': login_token,
                'format': 'json'
            }

            login_response = self.session.post(self.api_url, data=login_params)
            login_response.raise_for_status()
            login_result = login_response.json()

            if login_result.get('login', {}).get('result') == 'Success':
                self.logged_in = True
                return True
            else:
                print(f"Login failed: {login_result}")
                return False
        except Exception as e:
            print(f"Login error: {e}")
            return False

    def get_csrf_token(self):
        if 'csrf' in self.tokens:
            return self.tokens['csrf']

        params = {
            'action': 'query',
            'meta': 'tokens',
            'format': 'json'
        }

        try:
            response = self.session.get(self.api_url, params=params)
            response.raise_for_status()
            data = response.json()
            self.tokens['csrf'] = data['query']['tokens']['csrftoken']
            return self.tokens['csrf']
        except Exception as e:
            print(f"Error getting CSRF token: {e}")
            return ""

    def query(self, params):
        query_params = {
            'action': 'query',
            'format': 'json',
            **params.get('options', {})
        }

        try:
            response = self.session.get(self.api_url, params=query_params)
            response.raise_for_status()
            
            if not response.text:
                print("Warning: Empty response from server")
                return []
                
            data = response.json()

            if 'query' in data and 'logevents' in data['query']:
                return data['query']['logevents']
            return []
        except requests.exceptions.RequestException as e:
            print(f"Request error in query: {e}")
            return []
        except ValueError as e:
            print(f"JSON parsing error in query: {e}")
            if hasattr(response, 'text'):
                print(f"Response text: {response.text[:200]}...")
            return []

    def query_pages(self, params):
        query_params = {
            'action': 'query',
            'format': 'json',
        }

        if params.get('useIdsOrTitles') == 'titles':
            query_params['titles'] = params.get('titles')
        else:
            query_params['pageids'] = params.get('pageids')

        if 'options' in params:
            query_params.update(params['options'])

        try:
            response = self.session.get(self.api_url, params=query_params)
            response.raise_for_status()
            
            if not response.text:
                print("Warning: Empty response from server")
                return {}
                
            data = response.json()

            if 'query' in data and 'pages' in data['query']:
                return data['query']['pages']
            return {}
        except requests.exceptions.RequestException as e:
            print(f"Request error in query_pages: {e}")
            return {}
        except ValueError as e:
            print(f"JSON parsing error in query_pages: {e}")
            if hasattr(response, 'text'):
                print(f"Response text: {response.text[:200]}...")
            return {}

    def edit(self, params):
        try:
            csrf_token = self.get_csrf_token()
            if not csrf_token:
                print("Failed to get CSRF token for edit")
                return {"error": "No CSRF token"}
                
            edit_params = {
                'action': 'edit',
                'format': 'json',
                'token': csrf_token,
                **params
            }

            response = self.session.post(self.api_url, data=edit_params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Edit error: {e}")
            return {"error": str(e)}

def process_log(log_list):
    return [{'from': item['title'], 'to': item['params']['target_title']} for item in log_list]

def check_data_page(data):
    if data is None:
        return "no info"
    
    if data.get('redirect') is not None:
        return "redirect"
    
    if data.get('missing') is not None:
        return "missing"
    
    return "exist"

def get_page_status(pages_data, title):
    for page_id, page_data in pages_data.items():
        if page_data.get('title') == title:
            return check_data_page(page_data)
    return "no info"

def create_table(wiki_request, titles, max_titles=10):
    all_data = {}
    titles_list = list(titles)
    total_titles = len(titles_list)
    processed = 0
    
    print(f"Processing {total_titles} titles in batches of {max_titles}...")
    
    while titles_list:
        batch = titles_list[:max_titles]
        titles_list = titles_list[max_titles:]
        processed += len(batch)
        
        titles_str = '|'.join(batch)
        print(f"Querying batch {processed}/{total_titles} titles...")
        
        try:
            page_data = wiki_request.query_pages({
                'titles': titles_str,
                'useIdsOrTitles': 'titles',
                'options': {
                    'prop': 'info|redirects',
                    'rdprop': 'title'
                }
            })
            
            all_data.update(page_data)
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error processing batch: {e}")    
    return all_data

def processor(wiki_request, hamichlol_request, log_list, ns):
    string_data = ""
    obj_of_he = {
        "redirect": "הפניה",
        "missing": "לא קיים",
        "exist": "קיים",
        "no info": "???"
    }
    
    ns_strings = {
        0: "ערכים",
        10: "תבניות",
        14: "קטגוריות"
    }
    
    log_items = process_log(log_list)
    titles_set = set()
    
    for item in log_items:
        titles_set.add(item['from'])
        titles_set.add(item['to'])
    
    if not titles_set:
        print("No titles to process")
        string_data = "אין העברות חדשות בבדיקה זו.\n"
    else:
        print(f"Querying {len(titles_set)} titles from Hamichlol...")
        data_for_pages_local = create_table(hamichlol_request, titles_set)
        
        print(f"Querying {len(titles_set)} titles from Wikipedia...")
        data_for_pages_wiki = create_table(wiki_request, titles_set)
        
        print("Processing page status...")
        
        for item in log_items:
            item_from = item['from']
            item_to = item['to']
            
            local_from_status = get_page_status(data_for_pages_local, item_from)
            wiki_from_status = get_page_status(data_for_pages_wiki, item_from)
            local_to_status = get_page_status(data_for_pages_local, item_to)
            
            print(f"Title: {item_from}")
            print(f"  Local status: {local_from_status}")
            print(f"  Wiki status: {wiki_from_status}")
            
            skip_pattern = r'(BDSM|להט"ב|לט"ב|להטב"ק|לסבית|לסביות|סקסואל|קסואל|מצעד הגאווה|מיניות|פורנוגרפיה|\[\[פין\]\]|\[\[פות\]\])'
            
            if ((local_from_status == wiki_from_status and local_to_status == "exist") or 
                re.search(skip_pattern, item_to) or re.search(skip_pattern, item_from)):
                continue
            else:
                string_data += f"* [[:{item_from}]] <small>(מ: {obj_of_he[local_from_status]}, w: {obj_of_he[wiki_from_status]})</small> => [[:{item_to}]] <small>({obj_of_he[local_to_status]})</small>\n"
        
        if not string_data:
            string_data = "אין העברות חדשות בבדיקה זו.\n"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    edit_result = hamichlol_request.edit({
        'title': 'משתמש:מוטי בוט/יומן העברות ויקי',
        'text': f"{{{{טורים|תוכן=\n{string_data}}}}}\n@[[משתמש:נריה|נריה]] - דו\"ח העברות מתאריך {week_ago} עד {timestamp}. ~~~~",
        'summary': 'דו"ח העברות ויקי שבועי',
        'section': 'new',
        'sectiontitle': f'דו"ח העברות ויקי שבועי - {ns_strings.get(ns, "אחר")}',
        'nocreate': False
    })
    
    print(f"Edit result for namespace {ns}: {edit_result}")
    return edit_result

def query_with_continue(wiki_request, params, ns):
    all_results = []
    continue_params = {}
    
    current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.999Z")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    while True:
        query_params = {
            'options': {
                'list': 'logevents',
                'leprop': 'title|type|timestamp|comment|details',
                'letype': 'move',
                'lestart': current_time,
                'leend': week_ago,
                'lenamespace': ns,
                'lelimit': 'max',
                **continue_params
            }
        }
        
        results = wiki_request.query(query_params)
        all_results.extend(results)
        
        if 'continue' in wiki_request.session.get(wiki_request.api_url, params=query_params).json():
            continue_params = wiki_request.session.get(wiki_request.api_url, params=query_params).json()['continue']
        else:
            break
    
    return all_results

def run_for_namespace(wiki_request, hamichlol_request, ns):
    print(f"Processing namespace {ns}...")
    
    try:
        current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.999Z")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        res = wiki_request.query({
            'options': {
                'list': 'logevents',
                'leprop': 'title|type|timestamp|comment|details',
                'letype': 'move',
                'lestart': current_time, 
                'leend': week_ago,
                'lenamespace': ns,
                'lelimit': 'max'
            }
        })
        
        print(f"Found {len(res)} log entries for namespace {ns}")
        processor(wiki_request, hamichlol_request, res, ns)
    except Exception as e:
        print(f"Error running namespace {ns}: {e}")

def main():
    wiki_username = os.getenv('WIKI_USERNAME')
    wiki_password = os.getenv('WIKI_PASSWARD') 
    hamichlol_username = os.getenv('HAMICHLOL_USERNAME')
    hamichlol_password = os.getenv('HAMICHLOL_PASSWARD')

    wiki_request = WikiRequests("https://he.wikipedia.org/w/api.php")
    hamichlol_request = WikiRequests("https://www.hamichlol.org.il/w/api.php")
    
    print("Logging in to Wikipedia...")
    if not wiki_request.login(wiki_username, wiki_password):
        print("Failed to log in to Wikipedia. Exiting.")
        return
    
    print("Logging in to Hamichlol...")
    if not hamichlol_request.login(hamichlol_username, hamichlol_password):
        print("Failed to log in to Hamichlol. Exiting.")
        return
    
    print("Running for all namespaces...")
    run_for_namespace(wiki_request, hamichlol_request, 0)
    run_for_namespace(wiki_request, hamichlol_request, 14)
    run_for_namespace(wiki_request, hamichlol_request, 10)

if __name__ == "__main__":
    main()