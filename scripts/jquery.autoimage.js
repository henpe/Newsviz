/*##############################################################################
#    ____________________________________________________________________
#   /                                                                    \
#  |               ____  __      ___          _____  /     ___    ___     |
#  |     ____       /  \/  \  ' /   \      / /      /__   /   \  /   \    |
#  |    / _  \     /   /   / / /    /  ___/  \__   /     /____/ /    /    |
#  |   / |_  /    /   /   / / /    / /   /      \ /     /      /____/     |
#  |   \____/    /   /    \/_/    /  \__/  _____/ \__/  \___/ /           |
#  |                                                         /            |
#  |                                                                      |
#  |   Copyright (c) 2007                             MindStep SCOP SARL  |
#  |   Herve Masson                                                       |
#  |                                                                      |
#  |      www.mindstep.com                              www.mjslib.com    |
#  |   info-oss@mindstep.com                           mjslib@mjslib.com  |
#   \____________________________________________________________________/
#
#  Version: 1.0.0
#
#  (Svn version: $Id: jquery.autoimage.js 3437 2007-11-07 05:14:14Z herve $)
#
#----------[This product is distributed under a BSD license]-----------------
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions
#  are met:
#
#     1. Redistributions of source code must retain the above copyright
#        notice, this list of conditions and the following disclaimer.
#
#     2. Redistributions in binary form must reproduce the above copyright
#        notice, this list of conditions and the following disclaimer in
#        the documentation and/or other materials provided with the
#        distribution.
#
#  THIS SOFTWARE IS PROVIDED BY THE MINDSTEP CORP PROJECT ``AS IS'' AND
#  ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
#  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL MINDSTEP CORP OR CONTRIBUTORS
#  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
#  OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT
#  OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
#  BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
#  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
#  OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
#  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#  The views and conclusions contained in the software and documentation
#  are those of the authors and should not be interpreted as representing
#  official policies, either expressed or implied, of MindStep Corp.
#
################################################################################
#
#	This is a jQuery [jquery.com] plugin that implements image animations
#
#	@author: Herve Masson
#	@version: 1.0 (8/5/2007)
#	@requires jQuery v1.1.2 or later
#	
#	(Partly based on the legacy mjslib.org framework)
#
#	Dependencies: you need to load jquery.printf.js before this plugin
#
##############################################################################*/

/*
**	$('#image').autoimage({ options })
**
**	Options:
**
**	mouseover:
**		When true, animation progresses when the mouse is placed over the image.
**		Otherwise, animation runs contunously over time.
**
**	href:
**		specifies a link reference that will be associated with the image. When the
**		image is clicked, this link is handled the same way we set 'href'
**		to a <a> tag.
**
**	images:
**		this gives a list of secundary images to be displayed. For a mouseover
**		image, you only need one. For an animated image, you can use as many
**		as you want.
**
**	circular:
**		enable (when true) circular animation
**
**
*/

/*
**	                 =================================
**	                 >> Some Implementation details <<
**	                 =================================
**
**
**	A full animation cycle is represented by a 'pos' float value between 0 and 1:
**	=============================================================================
**
**
**	                        +--- current position
**	                        |
**	    0                   v                        1 <-- position value
**	    |---------=====|----x----=====|---------=====|
**	    |              |    ^         |              |
**	     \_ image1      \_ image2      \_ image3      \_ image4
**	       (slide1)       (slide2)       (slide3)       (slide4)
**
**
**	"-----"		the image is shown stable during this period of time
**	"====="		represents the smooth transition between images (crossfade)
**
**
**	In circular mode (loop=="cycle"):
**	=================================
**
**	The schema takes an extra slide so that the first image can follow
**	the last one.
**
**	                        +--- current position
**	                        |
**	    0                   v                                       1
**	    |---------=====|----x----=====|---------=====|---------=====|---------=====|...
**	    |              |    ^         |              |              |
**	    |    image1    |   image2     |   image3     |   image4     |     image1
**	    |   (slide1)   |  (slide2)    |  (slide3)    |  (slide4)    |    (slide1)
**
**
**	The amount of time spent in both stable and fade period is set via
**	the 'fade' parameter. It sets, in percentage, how long the fade
**	period lasts:
**
**	 - 100% means maximum fading (fadin occurs all along the slide period)
**	 - 0% means no fading
**	 - with 50%, stable and crossfading duration are equal
**	
**	
**	Internal representation:
**	========================
**
**	The whole sequence is converted into a list of regions. Each region is
**	defined by:
**
**	 - a length (a value in the 0...1 position domain)
**	 - an index representing the source image
**	 - an index representing the target image
**	 - a boolean that tells if this is a crossfade transition or not
**
**	For example, a non-cyclic animation made of 3 images with a fade parameter
**	set as 50% will be converted in 4 regions:
**
**	- region 1: source=0, target=undefined, length=.25, fade=false
**	- region 2: source=0, target=1, length=.25, fade=true
**	- region 3: source=1, target=undefined, length=.25, fade=false
**	- region 4: source=1, target=2, length=.25, fade=true
**
**	    0             .25              .5             .75             1 <-- position
**	    |---------------===============|---------------===============|
**	    |    region1        region2    |    region3        region4    | 
**	    |                              |                              | 
**	    |                              |                              | 
**	     \_ image1                      \_ image2                      \_ image3
**	       (slide1)                       (slide2)                       (slide3)
**
**
**	Note: I've done this representation so that we can specify arbitrary
**	transition durations in the future (for now, all slides have the same
**	region pattern). This will come in future revisions.
**
**
**	Looping
**	=======
**
**	By default, the image animation stops when it reaches a boundary (first or
**	last images). You can change that by giving a 'loop' parameter, which can
**	take those values:
**
**	  'none'     no looping (default)
**	  'cycle'    jump to the first image when we reach the last
**	  'bounce'   change direction when we reach the first or the last image
**
*/


(function($) {

	var TIMERINTERVAL=50;

	var LOOPMODES=
	{
		cycle:	{ cycle:true },
		bounce:	{ bounce: true }
	};

	var ISIE=jQuery.browser.msie;

	$.fn.extend(
		{
			autoimage:function(opts)
				{ return this.each(function() { return $.autoimage(this,opts); });			},

			aiButton:function(opts)
				{ return this.each(function() { return $.aiButton(this,opts); });			},

			aiApplyMarkupExtensions:function()
				{ return this.each(function() { return $.aiApplyMarkupExtensions(this); });	}
		}
	);

	$.autoimage=function(image,opts)
	{
		if(opts==undefined)
		{
			errorf("options are missing in autoimage()");
			return;
		}
		if(image.aimInfo!=undefined)
		{
			errorf("image is already assigned on element ID=%s",image.id);
			return;
		}

		var srclist=opts.images;

		/*
		** Creates a container for all images (they'll be shown one by one)
		** Note: to position images within the container, the
		** container needs to have a relative positioning (don't ask me why)
		*/

		$(image).wrap("<div></div>");
		var imcontainer=image.parentNode;
		imcontainer.style.position="relative";
		// Resizes the container to fit the image exactly
		resize(imcontainer,image.offsetWidth,image.offsetHeight);

		/*
		** Now, creates alternate image(s) and move them all in absolute positions
		** at offset 0:0 so that they all fit in the same screen space
		*/

		var imlist=[image];
		if(srclist!=undefined)
		{
			for(var i=1;i<=srclist.length;i++)
			{
				var im=document.createElement('img');
				im.src=srclist[i-1];
				imcontainer.appendChild(im);
				imlist[i]=im;
			}
		}

		for(var i=0;i<imlist.length;i++)
		{
			var im=imlist[i];
			im.style.position="absolute";
			im.style.top="0px";
			im.style.left="0px";
			im.border=0;
			if(i>0)
			{
				// Only keep the primary image visible for now
				$(im).hide;
			}
		}


		/*
		** Now deals with the href option
		*/

		if(opts.href)
		{
			$(imcontainer).wrap("<a></a>");
			var anchor=imcontainer.parentNode;
			anchor.href=opts.href;
		}

		if(imlist.length==1)
		{
			// No image animation, just a link
			return;
		}

		/*
		**	Parses options; build the AutoIMage information block,
		**	and attach it to the container
		*/

		var aim=imcontainer.aimInfo=image.aimInfo=
			{
				id:			image.id,
				images:		imlist,
				count:		imlist.length,
				fade:		opts.fade,
				speed:		opts.speed,
				bwspeed:	opts.bwspeed,
				fwspeed:	opts.fwspeed,
				mouseover:	opts.mouseover
			};

		var mode=opts.loop,val;
		if(mode!=undefined)
		{
			if((val=LOOPMODES[mode])==undefined)
			{
				errorf("unknown loop mode '%s'",mode);
			}
			else
			{
				aim.bounce=val.bounce;
				aim.cycle=val.cycle;
			}
		}
	
		// Computes animation speed values
		if(aim.speed==undefined)
		{
			aim.speed=$.autoimage.defaults.speed;
		}
		if(aim.fwspeed==undefined)
		{
			aim.fwspeed=aim.speed;
		}
		if(aim.bwspeed==undefined)
		{
			aim.bwspeed=aim.fwspeed;
		}
		if(aim.fwspeed>0)
		{
			aim.incfactor=1/aim.fwspeed;
		}

		if(aim.fade==undefined)
		{
			aim.fade=$.autoimage.defaults.fade;
		}
		if(aim.fade===true)
		{
			aim.fade=100;
		}

		/*
		**	Build the region map
		*/

		var nslices=(aim.cycle)?aim.count:aim.count-1;
		var regsz=1/nslices;
		var reglist=[],regidx=0

		for(var i=0;i<nslices;i++)
		{
			var next=(i+1)%aim.count;
			if(aim.fade>=100)
			{
				// Full fading mode (no stable image)
				reglist[regidx++]={ source:i, target:next, length: regsz, fade:true };
			}
			else if(aim.fade<=0)
			{
				// Non fading mode
				reglist[regidx++]={ source:i, length: regsz, fade:false };
			}
			else
			{
				var fadesz=(aim.fade*regsz)/100;
				var stsz=regsz-fadesz;
				reglist[regidx++]={ source:i, length: stsz, fade:false };
				reglist[regidx++]={ source:i, target: next, length: fadesz, fade:true };
			}
		}

		// Inserts an artificial region for the non-circular mode (last image in stable mode)
		if(!aim.cycle)
		{
			reglist[regidx++]={ source:(aim.count-1), length: 0, fade:false };
		}

		aim.regions=reglist;
		aim.regcount=reglist.length;

		/*
		**	Hook necessary event handlers
		*/

		if(opts.mouseover)
		{
			//	We want the image animation to run when the mouse is over the image
			$(imcontainer).hover(
				function(){return onMouseEnter(aim)},
				function(){return onMouseLeave(aim)}
			);
		}
		else
		{
			//	Time controls the animation
			startTimeAnim(aim);
		}

		// Starts at position 0

		setPosition(aim,0);
	}

	$.aiButton=function(image,opts)
	{
		if(opts==undefined)
		{
			errorf("options are missing in aiButton()");
			return;
		}
		if(opts.oversrc!=undefined)
		{
			opts.images=[opts.oversrc];
		}
		opts.mouseover=true;
		if(opts.fade)
		{
			opts.fwspeed=$.autoimage.defaults.buttons.fwspeed;
			opts.bwspeed=$.autoimage.defaults.buttons.bwspeed;
		}
		else
		{
			opts.speed=0;
		}
		return $.autoimage(image,opts);
	}


	/*
	**	Apply autoimage markup extensions
	**	=================================
	**
	**	Because I find writing javascript hooks overkilling for small features
	**	such as overstate images, I added this possibility to extend the HTML
	**	attributes of the image element.
	**
	**	If you want to create an overstate button with fading effect between
	**	the two state images, you would write this in your HTML:
	**
	**		<img src=image1 oversrc=image2 href="javascript:bingo()" fade="true">
	**		                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
	**	This markup extensions recognize the following non-conventional attributes:
	**
	**	- href: just set it as you would do with <a>
	**	- oversrc: set an overstate image
	**	- fade: set the fade value (ex: "yes","no","true","false",50,...)
	**
	**	Note: the HTML extensions are enabled by default.
	**
	*/

	function applyImageMarkup(image)
	{
		var opts={},href,oversrc,fade,doit=false;

		if(href=$(image).attr("href"))
		{
			opts.href=href;
			doit=true;
		}
		if(oversrc=$(image).attr("oversrc"))
		{
			opts.oversrc=oversrc;
			doit=true;
			if(fade=$(image).attr("fade"))
			{
				opts.fade=parseFade(fade);
			}
		}
		if(doit)
		{
			$(image).aiButton(opts);
		}
	}

	$.aiApplyMarkupExtensions=function(from)
	{
		from=from||document.body;

		$("img").each(function()
			{
				applyImageMarkup(this);
			});
	}

	/*
	**	              ========================================
	**	              >> Private code - do not use directly <<
	**	              ========================================
	*/


	/*
	**	Progress the animation
	**	======================
	**
	**	Change the animation position backward or forward, according to
	**	the current increment factor value. Stops the timer when we
	**	reached an end.
	**
	*/

	function onTimer(aim)
	{
		var now=curtime();

		if(aim.hoverlast==undefined)
		{
			aim.hoverlast=now;
		}

		var delta=now-aim.hoverlast;
		var inc=aim.incfactor*delta;
		var newpos=aim.pos+inc;

		if(!aim.cycle)
		{
			if(aim.bounce)
			{
				if(newpos>=1)
				{
					newpos=1;
					aim.incfactor=-1/aim.bwspeed;
				}
				else if(newpos<=0)
				{
					newpos=0;
					aim.incfactor=1/aim.fwspeed;
				}
			}
			else
			{
				// Clip the value in non circular mode
				newpos=newpos>1?1:newpos;
				newpos=newpos<0?0:newpos;
			}
		}

		setPosition(aim,newpos);
		aim.hoverlast=now;

		if(aim.incfactor<0 && newpos<=0)
		{
			// Backward animation finished -> we no longer need the timer
			stopHoverTimer(aim);
		}
	}


	/*
	**	Runs the animation continously
	**	==============================
	**
	*/

	function startTimeAnim(aim)
	{
		aim.timer=setInterval(function(){onTimer(aim);},TIMERINTERVAL);
	}

	/*
	**	Runs the animation on mouseover conditions:
	**	===========================================
	**
	**	In circular mode, the animation stops when the mouse leave the area,
	**	and restarts on next mouseenter at the same position.
	**
	**	In non circular mode, the animation goes backward when the mouse leave
	**	the area, until it reaches the position 0.
	**
	*/

	function stopHoverTimer(aim)
	{
		clearInterval(aim.timer);
		aim.timer=undefined;
		aim.hoverlast=undefined;
	}

	function onMouseEnter(aim)
	{
		if(aim.fwspeed<=0)
		{
			// speed=0 means instantly
			stopHoverTimer(aim);
			setPosition(aim,1);
			return;
		}
		aim.incfactor=1/aim.fwspeed;
		if(aim.timer==undefined)
		{
			aim.timer=setInterval(function(){onTimer(aim)},TIMERINTERVAL);
		}
	}

	function onMouseLeave(aim)
	{
		if(aim.bwspeed<=0)
		{
			// speed=0 means instantly
			stopHoverTimer(aim);
			setPosition(aim,0);
			return;
		}
		aim.incfactor=-1/aim.bwspeed;
		if(aim.cycle)
		{
			// circular mode: we stop where we are
			stopHoverTimer(aim);
		}
	}


	/*
	**	Set the animation position, and update image(s) accordingly
	**	===========================================================
	**
	**	This is the heart of this module. It select an arbitrary position
	**	within the animation, from 0 (start) to 1 (end).
	**
	*/

	function setPosition(aim,pos)
	{
		// Slide "size" (how much we spend in one frame)
		var slsize=1/aim.count;

		// Current image transparency
		var transp=0;

		// Current and next image indexes
		var curim;

		// Keep for later
		aim.pos=pos;

		// Sanitize the 'pos' value
		if(aim.cycle)
		{
			// In circular mode, we do modulo
			if(pos<0)
			{
				pos=pos-int(pos)+1;
			}
			if(pos>=1)
			{
				pos=pos-int(pos);
			}
		}
		else
		{
			// In non-circular mode, we do clipping (and the value 1 is okay)
			pos=pos<0?0:pos;
			pos=pos>1?1:pos;
		}

		// See if something changed since last time
		if(pos==aim.sanepos)
		{
			// We are already there
			return;
		}

		// Saves the sanitized value
		aim.sanepos=pos;

		// Parses the region list to see where we are
		var reg,regpos=pos;
		for(var i=0;i<aim.regcount;i++)
		{
			reg=aim.regions[i];
			if(reg.length>regpos)
			{
				break;
			}
			regpos-=reg.length;
		}

		if(!reg.fade)
		{
			// No crossfading here -> show the current image and hide others
			for(var i=0;i<aim.count;i++)
			{
				if(i==reg.source)
				{
					showOpaqueImage(aim.images[i]);
				}
				else
				{
					hideImage(aim.images[i]);
				}
			}
			return;
		}

		/*
		**	This is where it gets a little trickier - cross-fading
		**
		** See where we are in the image transition (0: source image, 1: dest image)
		** (This gives the opacity factor, also between 0 and 1)
		*/

		var opac=(regpos/reg.length);
		for(var i=0;i<aim.count;i++)
		{
			var im=aim.images[i];
			if(i==reg.target)
			{
				// Makes the target image the foreground image
				im.style.zIndex=1;
				setOpacity(im,opac);
				showImage(im);
			}
			else if(i==reg.source)
			{
				// Makes the source image the background image
				im.style.zIndex=0;
				showOpaqueImage(im);
			}
			else
			{
				// We don't need this one for now
				hideImage(im);
			}
		}
	}

	/*
	**	Misc utilities
	*/

	function showImage(im)			{ im.style.visibility="visible";	}
	function showOpaqueImage(im)	{ setOpacity(im,1); showImage(im);	}
	function hideImage(im)			{ im.style.visibility="hidden";		}
	function int(val)				{ return Math.floor(val);			}
	function curtime()				{ return (new Date()).getTime();	}

	if($.verrorf)
	{
		function errorf()	{ $.verrorf(arguments);	}
		function logf()		{ $.vlogf(arguments);	}
	}
	else
	{
		function errorf()	{ }
		function logf()		{ }
	}

	function setOpacity(elem,opac)
	{
		if(opac>=1 && !elem.aimHasOpac)
		{
			// Don't apply opacity filter when we never use a value != 1 before
			// (I am not sure if that worth it, but some browser might like it)
			return;
		}
		if(ISIE)
		{
			elem.style.filter="alpha(opacity=" + opac + ")";
		}
		else
		{
			elem.style.opacity=opac;
		}
		elem.aimHasOpac=true;
	}

	function resize(el,dx,dy)
	{
		if(dx != undefined)
		{
			el.style.width=dx+"px";
		}
		if(dy != undefined)
		{
			el.style.height=dy+"px";
		}
	}

	function parseFade(prm)
	{
		if(prm.constructor!=String)
		{
			return prm;
		}
		prm=prm.toLowerCase();
		// Parses the string value
		if(prm=="true" || prm=="yes")
		{
			return true;
		}
		if(prm=="false" || prm=="no")
		{
			return false;
		}
		var ival=parseInt(prm);
		if(isNaN(prm))
		{
			errorf("'%s' is not a legal value for 'fade' parameter",prm);
			return undefined;
		}
		return ival;
	}



$.autoimage.defaults=
{
	speed:			1000,		// default speed for image animation
	fade:			0,			// default fading factor, in percent

	// Defaults for aiButton()
	buttons:
		{
			fwspeed:	100,	// speed for the normal->over transition
			bwspeed:	300		// speed for the over->normal transition
		}
};

})(jQuery);

       
$(function() 
{
	jQuery.aiApplyMarkupExtensions();
})


