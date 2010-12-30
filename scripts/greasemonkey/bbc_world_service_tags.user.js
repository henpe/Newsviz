// ==UserScript==
// @name           BBC World Service tags
// @namespace      bbcws
// @include        http://www.bbc.co.uk/portuguese/*/*.shtml
// @include        http://www.bbc.co.uk/mundo/*/*.shtml
// @include        http://www.bbc.co.uk/russian/*/*.shtml
// @include        http://www.bbc.co.uk/persian/*/*.shtml
// @include        http://www.bbc.co.uk/turkce/*/*.shtml
// @include        http://www.bbc.co.uk/vietnamese/*/*.shtml
// @include        http://www.bbc.co.uk/zhongwen/*/*.shtml
// @include        http://www.bbc.co.uk/hindi/*/*.shtml
// @include        http://www.bbc.co.uk/arabic/*/*.shtml
// @exclude		   http://www.bbc.co.uk/*/index.shtml
// ==/UserScript==

// Singleton pattern.
var SemanticTags = (function () {
    //
    // Private variables
    //
    var THRESHOLD = 0.2;
	var langcode;
	var aggregation_url;

    //
    // Private functions
    //

    // This function builds the tag container.
	function renderContainer() {
        var node = document.getElementById("blq-content");
		node = node.getElementsByClassName("g-group")[1];
		node = node.getElementsByClassName("g-w8")[0];
		
		var div = document.createElement("div");
		div.setAttribute("id", "gm-semantic-tags");
		div.setAttribute("class", "g-container");
		div.setAttribute("style", "border-top:5px solid #E0E0E0; margin-bottom:1.38em; padding-top:0.46em;");

		var title = document.createElement("h2");
		title.appendChild(document.createTextNode("Tags"));
		title.setAttribute("style", "margin-bottom:10px; text-transform:uppercase;");
		
		var content = document.createElement("div");
		content.setAttribute("id", "gm-semantic-tags-content");
		content.setAttribute("style", "min-height:40px; background:url(http://dbpedia-i18n.appspot.com/images/progress.gif) 30% 30% no-repeat");
		
		var disclaimer = document.createElement("p");
		disclaimer.setAttribute("class", "disclaimer");
		disclaimer.innerHTML = "Powered by <a href=\"http://www.google.com\">Google</a> and <a href=\"http://www.zemanta.com\">Zemanta</a>";
	
		div.appendChild(title);
		div.appendChild(content);
		div.appendChild(disclaimer);
		
		node.insertBefore(div, node.firstChild); 	
	}
	
    function renderTags(json) {
		var tags = eval( "(" + json + ")" ).results;
		
		var content = document.getElementById("gm-semantic-tags-content");
		content.style.background = "";
		content.innerHTML = "";
console.log("js", tags);
		var places = tags.places;
		var people = tags.people;
		var events = tags.events;
		var subjects = tags.subjects;
		
		// Create places list
		if (places.length > 0) {
			var placesTitle = document.createElement("h3");
			placesTitle.innerHTML = "Places";
			placesTitle.setAttribute("style", "font-weight: normal; margin-bottom: 6px;");
			
			var placesList = document.createElement("ul");
			placesList.setAttribute("style", "margin-bottom: 10px;");
			
			var tagNode;
			for (i=0; i < places.length; i++) {
				tagNode = renderTag(places[i]);
				placesList.appendChild(tagNode);	
			}
			
			content.appendChild(placesTitle);
			content.appendChild(placesList);
		}
		
		// Create people list
		if (people.length > 0) {
			var peopleTitle = document.createElement("h3");
			peopleTitle.innerHTML = "People";
			peopleTitle.setAttribute("style", "font-weight: normal; margin-bottom: 6px;");
			
			var peopleList = document.createElement("ul");
			peopleList.setAttribute("style", "margin-bottom: 10px;");
			
			var tagNode;
			for (i=0; i < people.length; i++) {
				tagNode = renderTag(people[i]);
				peopleList.appendChild(tagNode);	
			}
			
			content.appendChild(peopleTitle);
			content.appendChild(peopleList);
		}
		
		// Create people list
		if (events.length > 0) {
			var eventsTitle = document.createElement("h3");
			eventsTitle.innerHTML = "Events";
			eventsTitle.setAttribute("style", "font-weight: normal; margin-bottom: 6px;");
			
			var eventsList = document.createElement("ul");
			eventsList.setAttribute("style", "margin-bottom: 10px;");
			
			var tagNode;
			for (i=0; i < events.length; i++) {
				tagNode = renderTag(events[i]);
				eventsList.appendChild(tagNode);	
			}
			
			content.appendChild(eventsTitle);
			content.appendChild(eventsList);
		}
		
		// Create subjects list
		if (subjects.length > 0) {
			var subjectsTitle = document.createElement("h3");
			subjectsTitle.innerHTML = "Subjects";
			subjectsTitle.setAttribute("style", "font-weight: normal; margin-bottom: 6px;");
			
			var subjectsList = document.createElement("ul");
			subjectsList.setAttribute("style", "margin-bottom: 10px;");
			
			var tagNode;
			for (i=0; i < subjects.length; i++) {
				tagNode = renderTag(subjects[i]);
				subjectsList.appendChild(tagNode);	
			}
			
			content.appendChild(subjectsTitle);
			content.appendChild(subjectsList);
		}
		
    }

	function renderTag(tag) {
		// Build tag link and attach it to list node
		var li = document.createElement("li");
		li.setAttribute("style", "display:inline-block; margin-bottom:4px; margin-right:4px;");
		
		var link = document.createElement("a");
		link.setAttribute("style", "display:block; color:#666; padding:4px; background-color:#ccc; -moz-border-radius:4px;");
		link.setAttribute("onmouseover", "this.style.backgroundColor=\"#900\"; this.style.color=\"#fff\";"); 
		link.setAttribute("onmouseout", "this.style.backgroundColor=\"#ccc\"; this.style.color=\"#666\";");
		link.setAttribute("title", tag.label["en"]);
		
		var resource = tag.id.split("http://dbpedia.org/resource/")[1];
		link.setAttribute("href", "http://newsviz.appspot.com/resource/" + resource);

		var label = (tag.label[langcode]) ? tag.label[langcode] : tag.label["en"];
		var en_suffix = (tag.label[langcode]) ? "" : " (en)";
		var text = document.createTextNode(label + en_suffix);
		
		link.appendChild(text);
		li.appendChild(link);
		
		return li;
	}
	
	function extractData(json) {
		var data = eval( "(" + json + ")" );
	}

    return {
        //
        // Public functions
        // (These access private variables and functions through "closure".)
        //

        // Initialize this script.
        init: function () {
			// Render tag container
			renderContainer();
		
            // Request tags
			var webservice = "http://newsviz.appspot.com/page/?url=";
			var url = window.location.href;
			
			if (url.indexOf("/portuguese/") != -1) {
				aggregation_url = "http://news.google.com/news?pz=1&ned=pt-PT_pt&hl=pt-PT&cf=all&scoring=n&q=site:bbc.co.uk/portuguese+";
				langcode = "pt";
			} else if (url.indexOf("/russian/") != -1) {
				aggregation_url = "http://news.google.com/news?pz=1&ned=ru_ru&hl=ru&cf=all&scoring=n&q=site:bbc.co.uk/russian+";
				langcode = "ru";
			} else if (url.indexOf("/mundo/") != -1) {
				aggregation_url = "http://news.google.com/news?pz=1&ned=es&hl=es&cf=all&scoring=n&q=site:bbc.co.uk/mundo+";
				langcode = "es";
			} else if (url.indexOf("/persian/") != -1) {
				aggregation_url = "http://search.bbc.co.uk/search?tab=persian&scope=persian&q=";
				langcode = "fa";
			} else if (url.indexOf("/vietnamese/") != -1) {
				langcode = "vi";
			}

			GM_xmlhttpRequest({
				'method': 'GET',
				'url': webservice + url,
				'onload': function (xhr) {
					renderTags(xhr.responseText);
				}
			});
        }
    };
}());
// End singleton pattern.

// Run this script.
SemanticTags.init();
