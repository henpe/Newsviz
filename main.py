import wsgiref.handlers
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'

from google.appengine.dist import use_library
use_library('django', '1.0')

import urllib
import logging
import sys
import codecs
import datetime
import time
import operator

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template
from google.appengine.ext import db
from google.appengine.api import urlfetch
from google.appengine.api.urlfetch import DownloadError 
from google.appengine.api import memcache
from google.appengine.api.labs import taskqueue

from django.utils import simplejson
from StringIO import StringIO
from urlparse import urlparse
from SPARQLWrapper import SPARQLWrapper, JSON
from BeautifulSoup import BeautifulSoup, Comment
from dateutil import parser
from dateutil import tz
import freebase

# Page class
class Page(webapp.RequestHandler):
    
    def get(self):
        self.url = self.request.get('url', '');
        self.api = self.request.get('api', 'zemanta');
        self.caller = self.request.get('caller', '');

        if self.url:
            try:
                self.analyze();
                self.response.headers['Content-Type'] = "application/json";
                simplejson.dump(self.values, self.response.out);
            except:
                logging.warning("Failed: " + self.url);
                simplejson.dump(None, self.response.out);
        else:
            print 'Please specify a URL';
    
    def analyze(self):
        self.freebase_ids = [];
        self.values = {"results":{}};
    
        # Check if this has already been analyzed recently
        key = self.url;
        
        #memcache.flush_all();
        cache = memcache.get(key);
        if cache is not None:
            self.values = cache;
        else:
            self.extract_concepts();
            
            # Add to memcache
            if not memcache.add(key, self.values):
                logging.error("Memcache set failed")
                
            # Clear pages memcache
            if not memcache.delete("/pages/"):
                logging.error("Memcache delete failed")
            if not memcache.delete("/pages/latest/"):
                logging.error("Memcache delete failed")
            if not memcache.delete("/pages/today/"):
                logging.error("Memcache delete failed")
    
    
    def extract_concepts(self):
        # Get page
        try: 
            page = urlfetch.fetch(self.url, headers={'Content-Type': 'charset=utf-8'});
        except:
            raise;
        
        # Extract text
        if page.status_code == 200:
            content = BeautifulSoup(page.content);
            site = self.url.split("/");
            self.site = site[0] + site[1] + "//" + site[2] + "/" + site[3] + "/"; # Dirty hack
            self.lang = content.find("meta", {"name" : "dc.language"})["content"];
            self.summary = content.find("meta", {"name" : "description"})["content"];
			
            self.keywords = u"";
            if content.find("meta", {"name" : "keywords"}):
                self.keywords = content.find("meta", {"name" : "keywords"})["content"];
			
            self.text = self.extract_content(content);
            
            if self.text:
                # Exctract title
                title = content.find(lambda tag: tag.name == "h1" and not tag.attrs);
                self.title = unicode(title.find(text=True));
            
                # Extract and convert date
                date = content.find("meta", {"name" : "dcterms.created"})["content"];
                self.date = parser.parse(date);

                # Translate content
                self.title_en = translate(self.title.encode('utf-8'), self.lang);
                self.summary_en = translate(self.summary.encode('utf-8'), self.lang);
                self.text_en = translate(self.text, self.lang);
                self.keywords_en = translate(self.keywords.encode('utf-8'), self.lang);

                if self.text_en:
                    # Extract keywords
                    if self.api == 'yahoo':
                        terms = self.extract_terms_yahoo();
                    elif self.api == 'alchemy':
                        terms = self.extract_terms_alchemy();
                    else:
                        terms = self.extract_terms_zemanta();
                        
                    # Add in lang tag
                    self.values["lang"] = self.lang;
                    self.values["terms"] = terms;
                    
                    # Extract types
                    self.extract_types();
                    
                # Store data
                self.store();
            
        else:
            print 'Error loading page';
        
        
    # Exctract content from page        
    def extract_content(self, content):
        title = content.find("h1");
        
        # Remove comments
        comments = content.findAll(text=lambda text:isinstance(text, Comment))
        [comment.extract() for comment in comments]
        
        # Remove AV Player text
        players = content.findAll("div", {"id" : "player"});
        [player.extract() for player in players]
        
        # Extract content fields
        content = content.find("div", {"class" : "bodytext"});
        
        # To prevent non WS stories going through (indexes, external links etc.)
        # Could probably be done better with try/catch block
        if content is None:
            return None;
        
        content = content.findAll(["h2", "p"]);
        
        text = u'' + unicode(title) + '. ';
        for item in content:
            try:
                text = text + item(text=True)[0] + u' ';
            except:
                text = text + u'';
        
        return text.encode('utf-8');
          
          
    # Exctract semantic terms using Zemanta API.
    # Translated keywords are passed in to improve results. 
    def extract_terms_zemanta(self):
        url = 'http://api.zemanta.com/services/rest/0.0/';
        params = [
            ("api_key", 't49mn7h9xuntet5k36ezmsyh'),
            ("method", 'zemanta.suggest_markup'),
            ("text", self.text_en),
            ("emphasis", self.keywords_en),
            ("return_categories", 'dmoz'),
            ("return_images", '0'),
            ("return_rdf_links", '1'),
            ("format", 'json')
        ];

        result = _query_webservice(url, params, 'POST');
        
        topics = result["markup"]["links"];
        del result["markup"]["text"];
        
        #topics = filter(lambda topic: topic["confidence"] >= 0.2, topics);
        
        # For each keyword find translated label and build up a list of freebase guids.
        for topic in topics:
            resources = topic["target"];
            del topic["anchor"];
            for resource in resources:
                url = resource["url"];
                if url.find("wikipedia") > 0:
                    topic["label"] = {"en" : resource["title"]};
                elif url.find("dbpedia") > 0:
                    resource["provider"] = "dbpedia"
                    topic["id"] = url;
                elif url.find("freebase") > 0:
                    resource["provider"] = "freebase"
                    id = url.split("http://rdf.freebase.com/ns")[1]
                    topic["guid"] = id
                    
                    self.freebase_ids.append(topic["guid"]);
                else:
                    resource["remove"] = 1;
                    
            resources = filter(lambda resource: "remove" not in resource, resources);
            topic["target"] = resources;
        
        return topics;
        

    # Exctract semantic terms using Alchemy API.
    def extract_terms_alchemy(self):
        url = 'http://access.alchemyapi.com/calls/text/TextGetRankedNamedEntities';
        params = [
            ("apikey", 'f8a88628fc533a62594b016775e14ca08633abb6'),
            ("text", self.text_en),
            ("outputMode", 'json')
        ];

        result = _query_webservice(url, params, 'POST');
        return result;
    
    
    # Organise results into subgroups (places, people, organizations, events and subjects)
    def extract_types(self):
        url = 'http://api.freebase.com/api/service/mqlread?'
        queries  = []
        self.values["results"] = {}
        self.values["results"]["places"] = []
        self.values["results"]["people"] = []
        self.values["results"]["organizations"] = []
        self.values["results"]["events"] = []
        self.values["results"]["subjects"] = []
        
        for id in self.freebase_ids:
            queries.append({
                "id": str(id), 
                "guid": None,
                "type": [],
                "name": None,
                "/location/location/geolocation" : {
                        "latitude" : None,
                        "longitude" : None,
                        "optional" : True
                },
                "/time/event/start_date": None
            })

        if len(queries) > 0:
            results = freebase.mqlreadmulti(queries)
            
            for value in self.values["terms"]:
                if "guid" in value:
                    guid = value["guid"]
                    
                    for result in results:
                        if result["id"] == guid:
                            value["type"] = "/subject"
                            value["guid"] = result["guid"][:1]
                            
                            if result["/location/location/geolocation"] is not None:
                                value["geolocation"] = result["/location/location/geolocation"]
                            
                            for type in result["type"]:
                                if type == "/people/person":
                                    value["type"] = type
                                    self.values["results"]["people"].append(value)
                                    break
                                    
                                elif type == "/location/citytown" or type == "/location/country" or type == "/location/administrative_division" or type == "/location/continent" or type == "/location/location":
                                    value["type"] = type
                                    self.values["results"]["places"].append(value)
                                    break
                                    
                                elif type == "/organization/organization" or type == "/organization/club" or type == "/business/company":
                                    value["type"] = type
                                    self.values["results"]["organizations"].append(value)
                                    break
                                    
                                elif type == "/time/event" and result["/time/event/start_date"]:
                                    value["type"] = type
                                    self.values["results"]["events"].append(value)
                                    break
                            
                            if value["type"] == "/subject":
                                self.values["results"]["subjects"].append(value)
                            
                            break
                            
        del self.values["terms"]
        

    # Get label in the page language from wikipedia.
    def get_translated_label(self, resource):
        url = 'http://en.wikipedia.org/w/api.php'
        params = [
            ("action", 'query'),
            ("prop", 'langlinks'),
            ("titles", resource["title"].encode('utf-8')),
            ("lllimit", '300'),
            ("format", 'json')
        ]

        result = _query_webservice(url, params, 'POST')
        if result["query"]:
            page_keys = result["query"]["pages"].keys()[0]
        else:
            return None
            
        label = None
        try:
            langlinks = result["query"]["pages"][page_keys]["langlinks"]
        
            for lang in langlinks:
                if lang["lang"] == self.lang[0:2]: # Hackish way of getting pt instead of pt-BR
                    label = lang["*"]
                    break

            return label
        except:
            return None

        
    # Store a resource in DB 
    def store_resource(self, resource, category):
        count = 1
        r = ResourceStore.get_by_key_name(resource["id"])
        if r:
            count = r.count
            count += 1
            
            try:
                memcache.delete(resource["id"])
            except:
                logging.info("Resource: Not memcached - " + resource["id"])
                
        else:
            r = ResourceStore(
                key_name = resource["id"],
                freebase_guid = resource["guid"],
                label = resource["label"]["en"],
                type = resource["type"],
                category = category
            )
            
            if "geolocation" in resource and (resource["geolocation"]["latitude"] and resource["geolocation"]["longitude"]):
                try:
                    r.point = db.GeoPt(resource["geolocation"]["latitude"], resource["geolocation"]["longitude"])
                except:
                    logging.warning("Geolocation failed: " + resource["id"])
                    
            #if category == "places":
                #get woeid
                
        
        r.count = count
        
        try:
            key = db.put(r)
        except:
            key = None
        
        return key

    
    # Store page in DB 
    def store(self):
        topics = self.values["results"];
        resources = [];

        # Only store page if it is not in the db already
        # Need to figure out how to update without increasing count
        page = PageStore.get_by_key_name(self.url);
        if page is None:
            
            # Page
            page = PageStore(
                key_name = self.url,
                site = self.site,
                lang = self.lang,
                date = self.date,
                title = self.title,
                summary = self.summary,
                title_en = self.title_en,
                summary_en = self.summary_en,
                json = simplejson.dumps(self.values)
            );
            
            db.put(page);
        
            # Place
            if "places" in topics:
                for resource in topics["places"]:
                    if "id" in resource:
                        key = self.store_resource(resource, "places")
                        if key:
                            resources.append(key)
            
            # Person
            if "people" in topics:    
                for resource in topics["people"]:
                    if "id" in resource:
                        key = self.store_resource(resource, "people")
                        if key:
                            resources.append(key)
                
            # Organization
            if "organizations" in topics:
                for resource in topics["organizations"]:
                    if "id" in resource:
                        key = self.store_resource(resource, "organizations")
                        if key:
                            resources.append(key)
                    
            # Event
            if "events" in topics:
                for resource in topics["events"]:
                    if "id" in resource:
                        key = self.store_resource(resource, "events")
                        if key:
                            resources.append(key)

            # Subject
            if "subjects" in topics:
                for resource in topics["subjects"]:
                    if "id" in resource:
                        key = self.store_resource(resource, "subjects")
                        if key:
                            resources.append(key)
            
            page.resources = resources;
                
            db.put(page);


# Resource class
class Resource(webapp.RequestHandler):
    def get(self):
        name = self.request.path.split('/')[2];
        if name:
            key = "http://dbpedia.org/resource/" + name;
            cache = memcache.get(key);
            if cache is not None:
                self.values = cache;
            else:
                self.values = {};

                resource = ResourceStore.get_by_key_name(key)
                
                self.values["type"] = resource.type
                self.values["id"] = resource.key().name()
                self.values["guid"] = resource.freebase_guid
                self.values["label"] = resource.label
                self.values["count"] = resource.count
                self.values["created"] = resource.created
                self.values["modified"] = resource.modified
                self.values["stats"] = {"languages": {}}
                
                if hasattr(resource, "point") and hasattr(resource.point, "lat"):
                    self.values["geolocation"] = {"latitude": resource.point.lat, "longitude": resource.point.lon}
                
                pages = []
                stats_languages = {}
                query = db.GqlQuery("SELECT * FROM PageStore WHERE resources = :1 ORDER BY modified DESC LIMIT 80", resource.key())
                for result in query:
                    page = {}
                    page["title"] = {"original": result.title, "translation": result.title_en}
                    page["summary"] = {"original": result.summary, "translation": result.summary_en}
                    page["url"] = result.key().name()
                    page["lang"] = result.lang
                    page["date"] = result.modified
                    page["site"] = result.site
                
                    if result.lang in self.values["stats"]["languages"]:
                        self.values["stats"]["languages"][result.lang] += 1
                    else:
                        self.values["stats"]["languages"][result.lang] = 1
                    
                    #date = str(result.created.date())
                    #if date in self.values["stats"]["dates"]:
                    #    self.values["stats"]["dates"][date] += 1
                    #else:
                    #    self.values["stats"]["dates"][date] = 1
                    
                    pages.append(page);
                    
                self.values["pages"] = pages[:80];
                
                try:
                    memcache.add(key, self.values);
                except:
                    logging.error("Resource: Memcache set failed - " + key);
                    
            # Render
            if self.request.get('render') == "json":
                json = simplejson.dumps(self.values, default=encode_datetime);
                if self.request.get('callback'):
                    json = "%s(%s)" % (self.request.get('callback'), json);
                            
                self.response.headers['Content-Type'] = "application/json";
                self.response.out.write(json);
                
            else:
                path = os.path.join(os.path.dirname(__file__), 'templates/resource.html')
                self.response.out.write(template.render(path, self.values));                     

        else:
            print 'Please specify a URL';
			

# Resources class
class Resources(webapp.RequestHandler):
    def get(self, category):

        store = None;
        type = self.request.get('type', None);
        limit = self.request.get('limit', '40');

        cache_key = self.request.path;
        cache = memcache.get(cache_key);
        if cache is not None:
            self.values = cache;
        else:
            self.values = {"results": {}};
            
            resources = [];
            if type:
                query = db.GqlQuery("SELECT * FROM ResourceStore WHERE category = :1 AND type = :2 ORDER BY count DESC LIMIT " + limit, category, type);
            else:
                query = db.GqlQuery("SELECT * FROM ResourceStore WHERE category = :1 ORDER BY count DESC LIMIT " + limit, category);
                
            for result in query:
                resource = {};
                resource["id"] = result.key().name();
                resource["guid"] = result.freebase_guid;
                resource["label"] = result.label;
                resource["count"] = result.count;
                resource["created"] = result.created;
                resource["modified"] = result.modified;
                resource["url"] = "http://newsviz.appspot.com" + resource["id"].split('http://dbpedia.org')[1];
                
                if hasattr(result, "type"):
                    resource["type"] = result.type;
                
                if hasattr(result, "point") and hasattr(result.point, "lat"):
                    resource["geolocation"] = {"latitude": result.point.lat, "longitude": result.point.lon};
                    
                resources.append(resource);

            #try:
            #    memcache.add("/places/", self.values);
            #except:
            #    logging.error("Memcache set failed");
        
        sorted_result = sorted(resources, key=operator.itemgetter('count'), reverse=True);
        
        self.values["results"][category] = resources;
        self.values["results"]["count"] = len(resources);
        
        if self.request.get('render') == "json":
            json = simplejson.dumps(self.values, default=encode_datetime);
            if self.request.get('callback'):
                json = "%s(%s)" % (self.request.get('callback'), json);
                        
            self.response.headers['Content-Type'] = "application/json";
            self.response.out.write(json);
            
        else:
            self.values["results"]["max"] = self.values["results"][category][0]["count"];
            self.values["results"]["type"] = type;
            self.values["results"]["category"] = category;
            
            path = os.path.join(os.path.dirname(__file__), 'templates/resources.html')
            self.response.out.write(template.render(path, self.values)); 
            

# Pages class
class Pages(webapp.RequestHandler):
    def get(self, type):
        
        cache_key = self.request.path;
        if type == "latest" or type == None:
            view = "latest"
            
        elif type == "today":
            view = "today"
            start_date = datetime.date.today();
            end_date = start_date + datetime.timedelta(days=1);
            
        else:
            date_string = type.strip('/')  # remove trailing slash
            date_string = date_string.split('/') 
            
            if len(date_string) == 3:
                view = "daily"
                year = int(date_string[0])
                month = int(date_string[1])
                day = int(date_string[2])
                delta = datetime.timedelta(days=1);
                
            elif len(date_string) == 2:
                view = "monthly"
                year = int(date_string[0])
                month = int(date_string[1])
                day = 1
                delta = datetime.timedelta(days=31);
                
            elif len(date_string) == 1:
                view = "yearly"
                year = int(date_string[0])
                month = 1
                day = 1
                delta = datetime.timedelta(days=365);

            start_date = datetime.date(year=year, month=month, day=day);
            end_date = start_date + delta;

        cache = memcache.get(cache_key);
        if cache is not None:
            self.values = cache;
        else:
            self.values = {"results": {"stats": {"languages": {}}}}
            
            pages = [];
            
            if view == "latest":
                timewindow = datetime.datetime.utcnow() - datetime.timedelta(hours=12);
                query = db.GqlQuery("SELECT * FROM PageStore WHERE modified > :1 ORDER BY modified", timewindow)
            else:
                query = db.GqlQuery("SELECT * FROM PageStore WHERE created > :1 AND created < :2 ORDER BY created", start_date, end_date)
                
            for result in query:
                page = {};
                page["title"] = {"original": result.title, "translation": result.title_en};
                page["summary"] = {"original": result.summary, "translation": result.summary_en};
                page["url"] = result.key().name();
                page["lang"] = result.lang;
                page["date"] = result.modified;
                page["site"] = result.site;
                topics = simplejson.loads(result.json);
                if topics["results"]:
                    page["places"] = topics["results"]["places"];
                    page["people"] = topics["results"]["people"];
                    page["organizations"] = topics["results"]["organizations"];
                    if "events" in topics["results"]:
                        page["events"] = topics["results"]["events"];
                        
                if result.lang in self.values["results"]["stats"]["languages"]:
                    self.values["results"]["stats"]["languages"][result.lang] += 1
                else:
                    self.values["results"]["stats"]["languages"][result.lang] = 1
                    
                pages.append(page);
            
            self.values["results"]["view"] = view;    
            self.values["results"]["pages"] = pages;
            self.values["results"]["count"] = len(pages);

            try:
                memcache.add(cache_key, self.values);
            except:
                logging.error("Memcache set failed");
        
        # Render
        if self.request.get('render') == "json":
            json = simplejson.dumps(self.values, default=encode_datetime);
            if self.request.get('callback'):
                json = "%s(%s)" % (self.request.get('callback'), json);
                        
            self.response.headers['Content-Type'] = "application/json";
            self.response.out.write(json);
            
        elif self.request.get('render') == "xml":
            sorted_result = sorted(self.values["results"]["pages"], key=operator.itemgetter('date'), reverse=True);
            self.values["results"]["pages"] = sorted_result;
            path = os.path.join(os.path.dirname(__file__), 'templates/pages.xml')
            self.response.out.write(template.render(path, self.values));
            
        else:
            sorted_result = sorted(self.values["results"]["pages"], key=operator.itemgetter('date'), reverse=True);
            self.values["results"]["pages"] = sorted_result;
            path = os.path.join(os.path.dirname(__file__), 'templates/pages.html')
            self.response.out.write(template.render(path, self.values)); 


# Stats class
class Stats(webapp.RequestHandler):
    def get(self, type):

        cache_key = self.request.path
            
        if type == "today" or type == None:
            view = "today"
            date = datetime.date.today()
            
        else:
            date_string = type.strip('/')  # remove trailing slash
            date_string = date_string.split('/') 
            
            if len(date_string) == 3:
                view = "daily"
                year = int(date_string[0])
                month = int(date_string[1])
                day = int(date_string[2])

            date = datetime.date(year=year, month=month, day=day)

        cache = memcache.get(cache_key)
        if cache is not None:
            self.values = cache
        else:
            self.values = {"results": {}}
            
            # Get stats
            query = db.GqlQuery("SELECT * FROM StatsStore WHERE date = :1", date)
            for result in query:
                self.values["results"] = self.analyze(result.stats)
                self.values["results"]["no_of_pages"] = result.no_of_pages
            
            # Get pages
            start_date = date
            end_date = start_date + datetime.timedelta(days=1)
            self.values["results"]["pages"] = {}   
            query = db.GqlQuery("SELECT * FROM PageStore WHERE date > :1 AND date < :2 ORDER BY date", start_date, end_date)
            for result in query:        
                key_name = result.key().name()
                self.values["results"]["pages"][key_name] = {"date": result.date, "lang": result.lang, "site": result.site, "title": {"translation": result.title_en, "original": result.title}, "summary": {"translation": result.summary_en, "original": result.summary}}

            self.values["results"]["view"] = view

            try:
                memcache.add(cache_key, self.values, 3600)
            except:
                logging.error("Memcache set failed")
            
        self.render()
   
     
    def analyze(self, json):
        stats = simplejson.loads(json)
        arrays = {"places": [], "people": [], "events":[], "organizations": []}
        for resource in stats["resources"]:
            type = stats["resources"][resource]["type"]
            if type.find("/location") != -1:
                arrays["places"].append(stats["resources"][resource])
            elif type.find("/people") != -1:
                arrays["people"].append(stats["resources"][resource])
            elif type.find("/event") != -1:
                arrays["events"].append(stats["resources"][resource])
            elif type.find("/organization") != -1 or type.find("/business") != -1:
                arrays["organizations"].append(stats["resources"][resource])

        for a in arrays:
            arrays[a].sort(key=operator.itemgetter('count'), reverse=True)
            
        stats["resources"] = arrays
        
        return stats
        
    
    def render(self):
        if self.request.get('render') == "json":
            json = simplejson.dumps(self.values, default=encode_datetime)
            if self.request.get('callback'):
                json = "%s(%s)" % (self.request.get('callback'), json)
                        
            self.response.headers['Content-Type'] = "application/json"
            self.response.out.write(json)
            
        elif self.request.get('render') == "xml":
            path = os.path.join(os.path.dirname(__file__), 'templates/stats.xml')
            self.response.out.write(template.render(path, self.values))
            
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates/stats.html')
            self.response.out.write(template.render(path, self.values))        
        

# ResourceStats class
class ResourceStats(webapp.RequestHandler):
    def get(self, name):
        
        cache_key = self.request.path
        
        cache = memcache.get(cache_key)
        if cache is not None:
            self.values = cache
        else:
            self.values = {}

            key = "http://dbpedia.org/resource/" + name
            resource = ResourceStore.get_by_key_name(key)
            
            end_date = datetime.datetime.today()
            start_date = end_date - datetime.timedelta(days=20)

            dates = {}
            
            delta = 19
            while delta > -1:
                date = end_date.date() - datetime.timedelta(days=delta)
                dates[str(date)] = {"count": {"total": 0}}
                delta = delta - 1

            query = db.GqlQuery("SELECT * FROM StatsStore WHERE resources = :1 AND date > :2 AND date < :3", resource.key(), start_date, end_date)
            for result in query:
                stats = simplejson.loads(result.stats)
                
                count = stats["resources"][key]["count"]
                dates[str(result.date.date())]["count"] = count
                
            self.values["dates"] = sorted(dates.items())
            
            try:
                memcache.add(cache_key, self.values, 3600)
            except:
                logging.error("Resource: Memcache set failed - " + cache_key)
            
        self.render()
   
    def render(self):
        if self.request.get('render') == "json":
            json = simplejson.dumps(self.values, default=encode_datetime)
            if self.request.get('callback'):
                json = "%s(%s)" % (self.request.get('callback'), json)
                        
            self.response.headers['Content-Type'] = "application/json"
            self.response.out.write(json)
            
        elif self.request.get('render') == "xml":
            path = os.path.join(os.path.dirname(__file__), 'templates/stats.xml')
            self.response.out.write(template.render(path, self.values))
            
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates/stats.html')
            self.response.out.write(template.render(path, self.values))     
            

# Get latest stories from Yahoo pipes and extract values
class PageWorker(webapp.RequestHandler):
    def get(self):
        
        url = 'http://viz.se/newsviz-proxy/?';
        params = [
            ("_id", 'xAk0qJNp3hGy8VaYOIGFTg'),
            ("_render", 'json')
        ];
        
        result = None;
        count = 0;
        while result is None:
            result = _query_webservice(url, params, 'GET');
            count += 1;
            if count == 3:
                break;
        
        self.response.headers['Content-Type'] = "application/json";
        simplejson.dump(result, self.response.out);
        
        if result:
            queue = taskqueue.Queue('page-worker');
            for item in result["value"]["items"]:
                key = item["link"];
                if PageStore.get_by_key_name(key) is None:
                    # Only add to queue if item hasn't been analyzed already
                    try:
                        task = taskqueue.Task(name = str(hash(item["link"])), url='/page/?url=' + item["link"] + '&caller=queue', method='GET');
                        queue.add(task);
                    except:
                        continue;


# Get latest stories from Yahoo pipes and extract values
class StatsWorker(webapp.RequestHandler):
    def get(self):
        today_date = datetime.date.today()
        today_time = datetime.time(hour=0, minute=0, second=0)
        start_date = datetime.datetime.combine(today_date, today_time)
        
        #q = db.GqlQuery("SELECT __key__ FROM StatsStore WHERE date < :1", start_date)
        #results = q.fetch(30)
        #db.delete(results) 
        
        #return
        
        #d = self.request.get('date').split('-')
        #start_date = datetime.datetime(year=int(d[0]), month=int(d[1]), day=int(d[2]))
        
        end_date = start_date + datetime.timedelta(days=1)
        last_updated = start_date
        key = str(start_date.date())
        
        daily_stats = StatsStore.get_by_key_name(key)
        if daily_stats:
            last_updated = daily_stats.modified        
        else:
            stats = {"resources": {}}
        
            daily_stats = StatsStore(
                key_name = key,
                date = start_date,
                no_of_pages = 0,
                stats = simplejson.dumps(stats, default=encode_datetime)
            )

        self.update_stats(daily_stats, start_date, last_updated, end_date)

        # Clear memcache
        if not memcache.delete("/stats/"):
            logging.error("/stats/: Memcache delete failed")
        if not memcache.delete("/stats/today/"):
            logging.error("/stats/today/: Memcache delete failed")
        if not memcache.delete("/stats/" + str(start_date.year) + "/" + str(start_date.month) + "/" + str(start_date.day) + "/"):
            logging.error("/stats/" + str(start_date.year) + "/" + str(start_date.month) + "/" + str(start_date.day) + "/: Memcache delete failed")

        self.response.headers['Content-Type'] = "application/json"
        self.response.out.write(daily_stats.stats)
    
            
    def update_stats(self, entity, start_date, last_updated, end_date):
        no_of_pages = entity.no_of_pages
        resources = entity.resources
        stats = simplejson.loads(entity.stats)

        # get pages that where modified since stats was last modifed
        query = db.GqlQuery("SELECT * FROM PageStore WHERE date > :1 AND date < :2 ORDER BY date", start_date, end_date)
        for result in query:
            if result.created < last_updated:
                continue
        
            no_of_pages += 1
            #key_name = result.key().name()
            
            #stats["pages"][key_name] = {"date": result.date, "lang": result.lang, "site": result.site, "title": {"translation": result.title_en, "original": result.title}, "summary": {"translation": result.summary_en, "original": result.summary}}
            
            for r in result.resources:
                if r not in resources:
                    resources.append(r)
            
            if result.resources:
                stats = self.extract_resources(stats, result)
            
        if len(resources) > 0:
            entity.resources = resources
            
        entity.no_of_pages = no_of_pages
        entity.stats = simplejson.dumps(stats, default=encode_datetime)
        
        db.put(entity)
        
    def extract_resources(self, stats, page):
        json = simplejson.loads(page.json)
        lang = json["lang"]

        for type in json["results"]:
            if type != "subjects":
                for resource in json["results"][type]:
                    if "id" in resource:
                        id = resource["id"]
                        if id not in stats["resources"]:
                            stats["resources"][id] = {}
                            stats["resources"][id]["label"] = resource["label"]
                            stats["resources"][id]["type"] = resource["type"]
                            stats["resources"][id]["url"] = "http://newsviz.appspot.com" + resource["id"].split('http://dbpedia.org')[1]
                            stats["resources"][id]["count"] = {}
                            stats["resources"][id]["pages"] = []
                            
                            if "geolocation" in resource:
                                stats["resources"][id]["geolocation"] = resource["geolocation"]
                        
                        stats["resources"][id]["pages"].append(page.key().name())
                        stats["resources"][id]["count"]["total"] = len(stats["resources"][id]["pages"])
                        
                        try: 
                            stats["resources"][id]["count"][lang] += 1
                        except:
                            stats["resources"][id]["count"][lang] = 1
                    
                            
        return stats
                    

# Present latest results on a dashboard
class Dashboard(webapp.RequestHandler):
    def get(self):
        template_values = {}
        
        path = self.request.path.split('/')[2];
        
        path = os.path.join(os.path.dirname(__file__), 'dashboard/' + path + '/index.html')
        self.response.out.write(template.render(path, template_values))
        
        

# Person class
class Person(webapp.RequestHandler):
    def get(self):
        cache = memcache.get("/person/latest")
        if cache is not None:
            self.values = cache
        else:
            self.values = {}
            self.values = self.get_latest(4)
            try:
                memcache.add("/person/latest", self.values, 630)
            except:
                logging.error("Resource: Memcache set failed - /person/latest")
        
        
        json = simplejson.dumps(self.values, default=encode_datetime);
        
        if self.request.get('callback'):
            json = "%s(%s)" % (self.request.get('callback'), json);
        
        self.response.headers['Content-Type'] = "application/json";
        self.response.out.write(json);

    
    def get_latest(self, limit):
        values = {"results": {}};
    
        persons = [];
        query = db.GqlQuery("SELECT * FROM ResourceStore WHERE category = 'people' ORDER BY modified DESC LIMIT 3");
        for result in query:
            person = self.get_person(result.key().name());
            
            persons.append(person);
            
        values["results"]["persons"] = persons;
        
        return values;
        
                            
    def get_person(self, key_name):
        person = ResourceStore.get_by_key_name(key_name);
        
        values = {"results": {}};
        
        values["id"] = person.key().name();
        values["guid"] = person.freebase_guid;
        values["label"] = person.label;
        values["count"] = person.count;
        values["created"] = str(person.created);
        values["modified"] = str(person.modified);
        
        pages = [];
        query = db.GqlQuery("SELECT * FROM PageStore WHERE resources = :1", person.key());
        for result in query:
            page = {};
            page["title"] = {"original": result.title, "translation": result.title_en};
            page["summary"] = {"original": result.summary, "translation": result.summary_en};
            page["url"] = result.key().name();
            page["lang"] = result.lang;
            page["date"] = result.date;
            page["site"] = result.site;
            
            pages.append(page);
            
        values["results"]["pages"] = pages;
               
        return values;


# Data model for a page
class PageStore(db.Model):
    site = db.StringProperty(required=True)
    lang = db.StringProperty(required=True)
    date = db.DateTimeProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    modified = db.DateTimeProperty(auto_now=True)
    title = db.StringProperty()
    summary = db.TextProperty()
    title_en = db.StringProperty()
    summary_en = db.TextProperty()
    json = db.TextProperty(required=True)
    resources = db.ListProperty(db.Key)

# Data model for a resource
class ResourceStore(db.Model):
    label = db.StringProperty()
    count = db.IntegerProperty()
    freebase_guid = db.StringProperty()
    woeid = db.StringProperty()
    category = db.StringProperty()
    type = db.StringProperty()
    point = db.GeoPtProperty()
    created = db.DateTimeProperty(auto_now_add=True)
    modified = db.DateTimeProperty(auto_now=True)
    stats = db.TextProperty()
    
# Data model for a resource
class StatsStore(db.Model):
    date = db.DateTimeProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    modified = db.DateTimeProperty(auto_now=True)
    no_of_pages = db.IntegerProperty()
    resources = db.ListProperty(db.Key)
    stats = db.TextProperty()


# Translate text into English using Goggle Translate
def translate(text, lang):
    url = 'http://ajax.googleapis.com/ajax/services/language/translate?';
    params = [
        ("langpair", lang + '|en'),
        ("q", text), 
        ("v", '1.0')
    ];

    result = _query_webservice(url, params, 'POST');
    
    if result["responseData"]:
        result = result["responseData"]["translatedText"].encode('utf-8');
    else: 
        result = None;
    
    return result;

# Query a webservice      
def _query_webservice(url, params, method):
    payload = urllib.urlencode(params);

    count = 0;
    request = None;
    while request is None:
        try:
            if method == 'POST':
                request = urlfetch.fetch(url = url, payload = payload, method = urlfetch.POST);
            else:
                url = url + payload;
                request = urlfetch.fetch(url, headers={'Content-Type': 'application/json; charset=utf-8', 'Accept-Encoding': 'gzip,deflate'});
        except DownloadError:
            count += 1;
            if count == 3:
                raise;

    result = None;
    if request.status_code == 200 and request.content:
        response = StringIO(request.content);
        try:
            result = simplejson.load(response);
        except ValueError:
            return result;
    
    return result;

# Override simplejson datetime serialization
def encode_datetime(obj):
	if isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date):
		return str(obj)
	raise TypeError(repr(o) + " is not JSON serializable")


def main():
  application = webapp.WSGIApplication(
                                       [('/page/', Page), (r'/pages/?(today|latest)?/?', Pages), (r'/pages/(\d{4}?/?\d{2}?/?)?', Pages), (r'/pages/(\d{4}?/?\d{2}?/?\d{2}?/?)?', Pages), (r'/stats/?(today)?/?', Stats), (r'/stats/(\d{4}?/?\d{2}?/?\d{2}?/?)?', Stats), (r'/(places|people|events|organizations|subjects)/?', Resources), (r'/resource/(.*)/stats/?', ResourceStats), ('/resource/.*', Resource), ('/person/.*', Person), ('/page/worker/', PageWorker), ('/stats/worker/', StatsWorker), ('/dashboard/.*', Dashboard)],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()