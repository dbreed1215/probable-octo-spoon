# CANNABIS/MARIJUANA LEGISLATION TRACKING
# CO General Assembly and US Congress
# Last Edited: 18 January 2023 by David Breed

from bs4 import BeautifulSoup,SoupStrainer
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import InvalidSessionIdException,NoSuchWindowException
from datetime import datetime,date
import time
import pandas as pd
import json
import os

# Check and edit before using; Not sure if the outfiles will work on Mac
# API keys are free and easy to get. Visit: https://api.congress.gov/sign-up/
outfile_national = os.path.join(os.path.expanduser('~'),'Downloads','national_'+datetime.strftime(date.today(),'%y%m%d')+'.csv')
outfile_state = os.path.join(os.path.expanduser('~'),'Downloads','state_'+datetime.strftime(date.today(),'%y%m%d')+'.csv')
api_key = ''



# Although their names are intuitive, the state session IDs are not intuitive, so this looks them up and we
# use them later as part of the url
def find_state_session_ids():
    # Makin' a lil' soup
    response = requests.get('https://leg.colorado.gov/bill-search')
    soup = BeautifulSoup(response.content,'lxml',parse_only=SoupStrainer(id='edit-field-sessions'))

    # There is a dropdown for state sessions, so this sees which options are available. It then gets info for the 2 most recent sessions
    state_session_names = [e.text for e in soup.find_all('option') if (str(e.text).startswith(str(date.today().year)) or str(e.text).startswith(str(int(date.today().year)-1)))]
    state_session_ids = [e['value'] for e in soup.find_all('option') if (str(e.text).startswith(str(date.today().year)) or str(e.text).startswith(str(int(date.today().year)-1)))]

    # Return the state session names and IDs
    return [state_session_names,state_session_ids]



# This runs the searches for both keywords (marijuana and cannabis). It then gets the url's for each piece of legislation, other
# obscure information like number of results per page of results, how many pages, etc. 
def find_state_links_and_general_info():
    
    # Create a temporary dataframe
    tempdf = pd.DataFrame(data=None,index=None,columns=['search_term','session_name','session_id','number_per_full_page','total_number_results','total_results_pages'])
    number_of_results = []
    
    # Get the session names and IDs
    session_names,ids = find_state_session_ids()
    
    # Loop through search terms then loop through sessions
    for search_term in ['marijuana','cannabis']:
        for session_id,session_name in zip(ids,session_names):
            
            # The data we gather in find_state_session_ids() controls part of this url.
            # Make a request and fetch the soup
            url = 'https://leg.colorado.gov/bill-search?search_api_views_fulltext={st}&field_chamber=All&field_bill_type=All&field_sessions={id}&sort_bef_combine=search_api_relevance%20DESC'.format(st=search_term,id=session_id)
            response = requests.get(url)
            soup = BeautifulSoup(response.content,'lxml',parse_only=SoupStrainer(id='main-content'))

            # If there are no search results, add a row to tempdf so that it knows to skip over it (I think...)             
            try:
                number_results_raw = soup.select_one('div > div.view-header').text
            except:
                tempdf = pd.concat([tempdf,pd.DataFrame(data={'search_term':[search_term],'session_name':[session_name],'session_id':[session_id],
                                                        'number_per_full_page':[0],'total_number_results':[0],'total_results_pages':[0]},
                                                        index=None)])
                continue
            
            # If there are search results, this is just basic string manipulation to get the number of results, number per page
            # number of pages, etc. There is probably an easier way for this using regex. 
            number_per_full_page = int(str(str(number_results_raw.split('-')[1]).split('of')[0]).lstrip().rstrip())
            total_number_results = int(str(str(number_results_raw.split('of')[1]).split('resul')[0]).lstrip().rstrip())
            if total_number_results <= number_per_full_page:
                total_results_pages = 1
            elif total_number_results % number_per_full_page == 0:
                total_results_pages = total_number_results // number_per_full_page
            else:
                total_results_pages = (total_number_results // number_per_full_page) + 1
                
            # Add this all to the dataframe containing the parameters for when we scrape for legislation; reset index to use iterrows
            tempdf = pd.concat([tempdf,pd.DataFrame(data={'search_term':[search_term],'session_name':[session_name],'session_id':[session_id],
                                'number_per_full_page':[number_per_full_page],'total_number_results':[total_number_results],
                                'total_results_pages':[total_results_pages]},index=None)])
            tempdf.reset_index(inplace=True,drop=True)

    # Use these later, create for now
    tempdf['link'] = ''
    tempdf['status'] = ''
    tempdf['statusdate'] = ''


    # Loop through tempdf and scrape the general info for each legislation
    for idx,row in tempdf.iterrows():
        # Create some empty lists
        page_hrefs,page_statusdates,page_statuses = ([] for i in range(3))

        # The page_strings is simply a part of the url that specifies which page of search results
        # The empty string is the first page of results because if not specified, it assumes page 1 of results
        if tempdf.at[idx,'total_number_results'] > 0:
            page_strings = ['']
            for p in [*range(1, tempdf.at[idx,'total_results_pages']+1)]:
                page_strings.append('&page={p}'.format(p=p))
            
            # Loop through each page of search results
            for page_string in page_strings:
                
                # Create the url from the search parameters in tempdf, scrape the HTML, turn into soup
                url = 'https://leg.colorado.gov/bill-search?search_api_views_fulltext={st}&field_chamber=All&field_bill_type=All&field_sessions={id}&sort_bef_combine=search_api_relevance%20DESC{ps}'.format(st=tempdf.at[idx,'search_term'],id=tempdf.at[idx,'session_id'],ps=page_string)
                response = requests.get(url)
                soup = BeautifulSoup(response.content, 'lxml', parse_only=SoupStrainer(id='main-content')) 
                
                # I can't remember what this does, but presumably it's important.
                # Find all pieces of legislation and loop through them
                for bill in soup.find_all('h4'):
                    if str(bill.select_one('a')['href']).startswith('http'):
                        page_hrefs.append(str(bill.select_one('a')['href']))
                    else:
                        page_hrefs.append('https://leg.colorado.gov' + str(bill.select_one('a')['href']))
                
                # Find the general status of the legislation
                for status in soup.find_all('div',{'class':'bill-last-action search-result-single-item'}):
                    lstatus_date,lstatus = str(status.text).split(' | ')
                    page_statusdates.append(lstatus_date.replace("\n",'').replace('Last Action: ',''))
                    page_statuses.append(lstatus.replace("\n",''))
        
        # Add these lists as 'cells' in the dataframe
        tempdf.at[idx,'link'] = page_hrefs
        tempdf.at[idx,'status'] = page_statuses
        tempdf.at[idx,'statusdate'] = page_statusdates
        
    # We have a weird dataframe with some 'cells' containing lists, so a simple reshape probably won't work. This creates
    # a new dataframe, then loops through tempdf and populates the new dataframe, Skip if no results
    tempdf1 = pd.DataFrame(data=None,index=None,columns=['session_name','link','status','statusdate'])
    tempdf.reset_index(inplace=True,drop=True)
    for idx,row in tempdf.iterrows():
        if len(tempdf.at[idx,'link']) > 0:
            for link,status,statusdate in zip(tempdf.at[idx,'link'],tempdf.at[idx,'status'],tempdf.at[idx,'statusdate']):
                tempdf1 = pd.concat([tempdf1,pd.DataFrame(data={'session_name':[row['session_name']],
                                                     'link':[link],'status':status,'statusdate':statusdate},index=None)])
        else:
            continue
    
    # Can't remember why the datetime stuff. Dropping duplicates gets rid of legislation that came up under both search terms        
    tempdf1['statusdate'] = pd.to_datetime(tempdf1['statusdate'],infer_datetime_format=True)
    tempdf1 = tempdf1.drop_duplicates(subset=['link'])
    tempdf1 = tempdf1.reset_index(drop=True)
    
    # Return the dataframe of details for each piece of legislation
    return tempdf1



# This loops through df_state_tosearch, get the relevant info for each piece
# of legislation, then adds it to our dataframe
def scrape_state_details(df_state,df_state_tosearch):

    # Loop through each row of legislation
    for idx,row in df_state_tosearch.iterrows():

        # Get the url, scrape the HTML, then make into soup (Yum...)
        url = df_state_tosearch.at[idx,'link']
        response = requests.get(url)
        soup = BeautifulSoup(response.content,'lxml',parse_only=SoupStrainer(id='main-content'))

        # Get the legislation name, number, description, type
        lname = soup.select_one('article > header > h1').text
        lnumber = soup.select_one('article > header > div > div > div').text
        ldescription = soup.select_one('article > header > div:nth-of-type(2) > div > div').text
        if 'r' in str(lnumber).lower():
            ltype = 'Resolution'
        elif 'm' in str(lnumber).lower():
            ltype = 'Memorial'
        else:
            ltype = 'Bill'

        # When Colorado passed Proposition 64, it mandated that marijuana tax revenue from adult use marijuana be directed
        # toward schools. This means that some search results are pieces of legislation that have nothing substantive to
        # do with marijuana, but rather in the funding part of the bill states that it should be funded from marijuana tax.
        # In other to ignore these education bills, this if-or statement deals with that.
        if ('marijuana' in str(lname).lower()) or ('marijuana' in str(ldescription).lower()) or ('cannabis' in str(lname).lower()) or ('cannabis' in str(ldescription).lower()):

            # The aside is in the aside part of the HTML. Difficult to scrape, but SoupStrainer helps a lot
            # Gets the sponsors of the bill, then cleans it up to be a single string.
            soup_aside = BeautifulSoup(response.content,'lxml',parse_only=SoupStrainer(class_='aside'))
            lsponsors = []
            for elem in soup_aside.find_all('div',{'class':'sponsor-item'}):
                lsponsors.append(elem.select_one('div > div:nth-of-type(2) > h4').text)
            lsponsors = ', '.join(lsponsors)

            # The bottom is in the bottom part of the HTML. This contains the legislation status. They display
            # it in a way that's hard to scrape because it contains the current status and previous statuses, so
            # this puts all statuses into a list then create the end (-1) element of the list
            soup_bottom = BeautifulSoup(response.content,'lxml',parse_only=SoupStrainer(class_='region region-bottom'))
            templist = soup_bottom.select_one('div > div:nth-of-type(2) > div > div > div').find_all('div')
            templist = [str(e.text).replace("\n",'').lstrip().rstrip() for e in templist if len(str(e.text)) > str(e.text).count(' ') and str(e.text) != '']
            lstatus_templist = []
            for e in templist:
                if not e in lstatus_templist:
                    lstatus_templist.append(e)
            lstatus_gen = lstatus_templist[-1]
        else:
            continue

        # Clean up the dates
        status_date = datetime.strftime(row['statusdate'],'%d-%b-%Y')
        update_timestamp = datetime.strftime(datetime.now(),'%d-%b-%Y %H:%M:%S')
        days_since_change = int(round((datetime.now()-row['statusdate']).days))

        # Add as new row to the main dataframe
        df_state = pd.concat([df_state,pd.DataFrame(data={'Session':[row['session_name']],'Legislation Number':[lnumber],'Type':[ltype],
                              'Name':[lname],'General Status':[lstatus_gen],'Description':[ldescription],'Date of Last Action':[status_date],
                              'Last Action':[row['status']],'URL':[row['link']],'Sponsors':[lsponsors],'Updated':[update_timestamp],
                              'Days Since Last Action':days_since_change},index=None)])

    # Do some final cleanup
    df_state = df_state.sort_values(by=['Days Since Last Action'])
    df_state = df_state.drop_duplicates()
    df_state = df_state.reset_index(drop=True)

    # Return the dataframe with all of the state legislation info that we scraped
    return df_state



# This is the url the user will use if they want to read more about the legislation. The other url is just for API calls.
def find_national_user_url(tempdict,ltype_main):

    # Uses the dict_user_url dictionary to find the code for the legislation type. This is needed for the user url.
    dict_user_url={'hr': 'house-bill','s': 'senate-bill',
                   'hjres': 'house-joint-resolution','sjres': 'senate-joint-resolution',
                   'hconres': 'house-concurrent-resolution','sconres': 'senate-concurrent-resolution',
                   'hres': 'house-resolution','sres': 'senate-resolution',
                   'hamdt': 'house-amendment','samdt': 'senate-amendment'}
    ltype_specific = dict_user_url[str(tempdict['type']).lower()]

    # Deals with numbering of the congresses (117th, 118th, etc.)
    if str(tempdict['congress'])[-1]=='1':
        sstr='st'
    elif str(tempdict['congress'])[-1]=='2':
        sstr='nd'
    else:
        sstr='th'

    # Use all the relevant details and return the user url as a string
    return 'https://www.congress.gov/{ltype_main}/{lsesh}{sstr}-congress/{ltype_specific}/{lnum}'.format(ltype_main=ltype_main,lsesh=tempdict['congress'],sstr=sstr,ltype_specific=ltype_specific,lnum=tempdict['number'])



# This finds which congress sessions to scrape based on whenever the script is ran in the next 200 years
def find_national_session_ids():
    counter = 0
    congress = 116
    dict_session = {}                           # Here is the logic of this: Starting in 2019 when it was
    for year in [*range(2019,2222)]:            # in session 116, then 117 started in 2021 when counter=2
        counter += 1                            # in the code to the left, so every time that counter
        dict_session.update({year:congress})    # reaches 2 (since sessions last 2 years) we advance to
        if counter == 2:                        # next congress number. Then, we use our dictionary to
            congress += 1                       # find the current session and the sessions before it
            counter = 0                         # Finally, we return all of that as a list.
        else:
            continue
    return [dict_session[date.today().year],dict_session[date.today().year]-1]



# Opens up a chromedriver for a couple seconds and gets the legislation number of
# those that have to do with marijuana or cannabis
def scrape_national_legislation_numbers():

    # Set up our driver. ChromeDriverManager is a super handy tool; otherwise you need to get a new chromedriver every time you update chrome
    driver=webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))

    # Use our function to find which congress sessions
    session_ids = find_national_session_ids()

    # Create a dataframe to which we will append (technically, concat) the data we get from the scrape
    df_national_tosearch=pd.DataFrame(columns=['lnum_full','lnum','ltype_abrv','lsesh'],index=None)

    # Search for two terms
    for search_term in ['marijuana','cannabis']:

        # It's possible/probable that we are scraping 2 sessions at one. This changes the url to search either one or two sessions.
        if len(session_ids) > 1:
            url = 'https://www.congress.gov/quick-search/legislation?wordsPhrases={st}&wordVariants=on&congressGroups%5B%5D=0&congresses%5B%5D={s1}&congresses%5B%5D={s2}&legislationNumbers=&legislativeAction=&sponsor=on&representative=&senator=&pageSize=250'.format(st=search_term,s1=session_ids[1],s2=session_ids[0])
        else:
            url = 'https://www.congress.gov/quick-search/legislation?wordsPhrases={st}&wordVariants=on&congressGroups%5B%5D=0&congresses%5B%5D=117&legislationNumbers=&legislativeAction=&sponsor=on&representative=&senator=&pageSize=250'.format(st=search_term,s1=session_ids[0])

        # Tells chromedriver to open the url
        driver.get(url)

        # Soup...yum; SoupStrainer tells beautifulsoup to only look at the content within the id='main' section of HTML
        # Chromedriver got the page loaded, and now passes the HTML to beautifulsoup with driver.page_source. Selenium
        # is opening the website because beautifulsoup and requests kept pulling the HTML before congress.gov loaded. ::sigh::
        soup = BeautifulSoup(driver.page_source,'lxml',parse_only=SoupStrainer(id='main'))

        # Finds each row of search results, then loops through them
        for row in soup.find_all('li',{'class':'compact'}):

            # This is the bill number as it will appear on the website
            lnum_full = str(row.select_one('span:nth-of-type(1) > a').text).replace('.','').lstrip().rstrip()

            # Since we have 2 search terms, we want to avoid duplicates in case a bill shows up with both search terms
            if not lnum_full in df_national_tosearch['lnum_full'].to_list():

                # Bill number to be used for API requests; Abbreviated type of legislation (used in API request); Session number
                lnum = int(''.join([l for l in str(lnum_full) if str(l).isdigit()]))
                ltype_abrv = str(''.join([l for l in str(lnum_full) if str(l).isalpha()])).lower()
                lsesh = int(str(str(row.select_one('span:nth-of-type(1)').text).split(' — ')[1])[:3])

                # Add it to the dataframe of search parameters we will need
                df_national_tosearch = pd.concat([df_national_tosearch,pd.DataFrame(data={'lnum_full':[lnum_full],'lnum':[lnum],'ltype_abrv':[ltype_abrv],'lsesh':[lsesh]})])

                # We will be using the pandas iterrows() function, so we will reset the index to start at 0,1,2,3,4...
                df_national_tosearch.reset_index(inplace=True,drop=True)
            else:
                continue

    # Just to give you time so you can see whether the page appears to load properly before shutting the chrome window
    try:
        time.sleep(1)
        driver.close()
    except(UnboundLocalError,InvalidSessionIdException,NoSuchWindowException):
        pass

    # Return the dataframe with the search criteria
    return df_national_tosearch



# Beautifulsoup and Selenium already got us all of the search criteria we need to use the congress.gov API. The API docs
# do not state a way to search for legislation with their API, but only get the info for specific bills...so we already
# have all of those search criteria in a dataframe
def fetch_from_congress_api(df_national,df_national_tosearch):

    # Loop through each bill
    for idx,row in df_national_tosearch.iterrows():

        # What type of legislation is it? This will affect our search url, so this figures that out
        if str(row['ltype_abrv']).lower() in ['hamdt','samdt']:
            url_get = 'https://api.congress.gov/v3/amendment/'+str(row['lsesh'])+'/'+str(row['ltype_abrv'])+'/'+str(row['lnum'])+'?api_key='+str(api_key)+'&format=json'
            ltype = 'amendment'
        elif str(row['ltype_abrv']).lower() in ['hr','s','hjres','sjres','hconres','sconres','hres','sres']:
            url_get = 'https://api.congress.gov/v3/bill/'+str(row['lsesh'])+'/'+str(row['ltype_abrv'])+'/'+str(row['lnum'])+'?api_key='+str(api_key)+'&format=json'
            ltype = 'bill'
        else:
            url_get = None
            ltype = None

        # Standard API call, then gets everything as json
        response = requests.get(url_get)
        dict_json = json.loads(response.content)

        # Session; legislation number; legislation name, date of last action, last action,
        # user url, sponsor, sponsor state, date updated, days since most recent action
        # Action date has two values. One is a string and the other is a date (datetime date class)
        lsesh = row['lsesh']
        lnum_full = row['lnum_full']
        if ltype == 'bill':                         # Because technically amendments
            lname = dict_json[ltype]['title']       # do not have titles
        elif ltype == 'amendment':
            lname = 'An amendment to {lt}{lnum} {lname}'.format(lt=dict_json[ltype]['amendedBill']['type'],lnum=dict_json[ltype]['amendedBill']['number'],lname=dict_json[ltype]['amendedBill']['title'])
        else:
            lname = None
        action_date_dt = date(datetime.strptime(dict_json[ltype]['latestAction']['actionDate'],'%Y-%m-%d').year,datetime.strptime(dict_json[ltype]['latestAction']['actionDate'],'%Y-%m-%d').month,datetime.strptime(dict_json[ltype]['latestAction']['actionDate'],'%Y-%m-%d').day)
        action_date = datetime.strftime(datetime.strptime(dict_json[ltype]['latestAction']['actionDate'],'%Y-%m-%d'),'%d-%b-%Y')
        action = dict_json[ltype]['latestAction']['text']
        url_user = find_national_user_url(dict_json[ltype],ltype)
        lsponsor = str(str(dict_json[ltype]['sponsors'][0]['fullName']).split('[')[0]).split('(')[0]
        lsponsor_st = dict_json[ltype]['sponsors'][0]['state']
        updated = datetime.strftime(datetime.now(),'%d-%b-%Y %H:%M:%S')
        dayssinceaction = (date.today()-action_date_dt).days

        # Take all the info we fetched and update our dataframe (concat); reset index is needed in order to avoid strangeness
        df_national = pd.concat([df_national,pd.DataFrame(data={'Session':[lsesh],'Legislation Number':[lnum_full],'Name':[lname],
                                    'Date of Last Action':[action_date],'Last Action':[action],'URL':[url_user],'Sponsor':[lsponsor],
                                    'Sponsor State':[lsponsor_st],'Updated':[updated],'Days Since Last Action':[dayssinceaction]},
                                    index=None)])
        df_national.reset_index(inplace=True,drop=True)

    # Clean everything up, sort the values, then reset the index
    df_national['Days Since Last Action'] = df_national['Days Since Last Action'].astype(int)
    df_national.sort_values(by=['Days Since Last Action','Legislation Number'],inplace=True)
    df_national.reset_index(inplace=True,drop=True)

    # Return the neat and tidy dataframe
    return df_national



# Just creates and returns two empty dataframes to which we append the data
def create_main_dataframes():
    df_state = pd.DataFrame(data=None,index=None,columns=['Session','Legislation Number','Type','Name','General Status','Description','Date of Last Action','Last Action','URL','Sponsors','Updated','Days Since Last Action'])
    df_national = pd.DataFrame(data=None,index=None,columns=['Session','Legislation Number','Name','Date of Last Action','Last Action','URL','Sponsor','Sponsor State','Updated','Days Since Last Action'])
    return [df_state,df_national]



# Simple. Saves the dataframes as csv
def save_dataframes(dfs,filepaths):
    for df,filepath in zip(dfs,filepaths):
        df.to_csv(filepath,index=False,header=True,na_rep='')

    # Return the filepaths so the person running the script knows where they are
    return filepaths



# MAIN - MAIN - MAIN - MAIN - MAIN
if __name__ == '__main__':

    # Create two empty dataframes
    df_state,df_national = create_main_dataframes()

    # Get the url parameters we will need for the CO Gen Assembly scraping
    df_state_tosearch = find_state_links_and_general_info()

    # Loops though df_state_tosearch and scrapes all the info using beautifulsoup
    df_main_state = scrape_state_details(df_state,df_state_tosearch)

    # Get the search criteria we will need for the US Congress API
    df_national_tosearch = scrape_national_legislation_numbers()

    # Loops through df_national_tosearch and gets all the info from the API
    df_main_national = fetch_from_congress_api(df_national,df_national_tosearch)

    # Save the two dataframes
    filepaths = save_dataframes([df_main_state,df_main_national],[outfile_state,outfile_national])

    # All done!!! Print the filepaths where the data is stored
    print('\nAll done! Your files are saved at:')
    for f in filepaths:
        print(f)