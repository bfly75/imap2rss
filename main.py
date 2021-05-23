#!/usr/bin/python
# -*- coding: utf-8 -*-
import toml
from flask import Flask, request, make_response, abort
from feedgen.feed import FeedGenerator
import imaplib, email
from email.header import decode_header
import pprint

app = Flask(__name__)

class EmailClient(object):
	def decode_email(self,string,idx=0):
		app.logger.info(str(decode_header(string)))
		if idx < len(decode_header(string)):
			if decode_header(string)[idx][1] is not None:
				return decode_header(string)[idx][0].decode(decode_header(string)[idx][1])
			else:
				return decode_header(string)[idx][0]
		else:
			return ""

	def __init__(self, rss_name):
		self.rss_name = rss_name
		self.imapname = config['rss'][self.rss_name]['imap']
		self.mailserver = imaplib.IMAP4_SSL(config['imap'][self.imapname]['server'])
		self.mailserver.login(config['imap'][self.imapname]['username'], config['imap'][self.imapname]['password'])
		if " " in config['rss'][self.rss_name]['mailbox']:
			self.mailbox = config['rss'][self.rss_name]['mailbox'].strip("'").strip('"')
			self.mailbox = f'"{self.mailbox}"'

	def listBox(self):
		import datetime
		self.mailserver.select(self.mailbox)
		date = (datetime.date.today() - datetime.timedelta(config['imap'][self.imapname].get('lastdays',90))).strftime("%d-%b-%Y")
		typ, msgnums = self.mailserver.uid('search', None, "(SENTSINCE {date})".format(date=date))
		#TODO check typ, OK if successfull.
		return msgnums[0].split()

	def _getBody(self, mail):
		charset = mail.get_content_charset()
		#print(f"Charset: {charset}")
		#print(f"Payload: {mail.get_payload(decode=True)}")
		#print(f"Content type: {mail.get_content_type()}")
		#print(f"Multipart: {mail.is_multipart()}")
		if mail.is_multipart():
			#print("=== Entering multipart processing")
			bodies = {}
			for part in mail.get_payload():
				#print(f"--- Payload of part of multipart: {part}")
				body, t = self._getBody(part)
				bodies[t] = body
				#print(f"--- Type: {t}")
				#print(f"--- Body: {body}")
				#if body != None:
				#	return body, t
			if 'text/html' in bodies and bodies['text/html'] != None:
				#print("Return text/html")
				return bodies['text/html'], 'text/html'
			elif 'text/plain' in bodies and bodies['text/plain'] != None:
				#print("Return text/plain")
				return bodies['text/plain'], 'text/plain'
			else:
				#print("Return None")
				return None, None
		elif mail.get_content_type() == 'text/html':
			#print(f"=== Entering text/html processing")
			return mail.get_payload(decode=True).decode(charset, 'ignore'), mail.get_content_type()
		elif mail.get_content_type() == 'text/plain':
			#print(f"=== Entering text/plain processing")
			return '<pre>'+mail.get_payload(decode=True).decode(charset, 'ignore')+'</pre>', mail.get_content_type()
		else:
			return None, None

	def _getAttachment(self, mail, cid):
		if mail.is_multipart():
			for part in mail.get_payload():
				attach, typ = self._getAttachment(part, cid)
				if attach != None:
					return attach, typ
		elif mail.get('Content-ID'):
			if mail.get('Content-ID')[1:-1] == cid:  ## Remove <> from cid
				return mail.get_payload(decode=True), mail.get_content_type()
		return None, None

	def cid_2_images(self, body, msgn):
		'''this replaces the <img src="<cid:SOMETHING>"/> tags with <img src="SOME URL"/> tags in the message'''
		from bs4 import BeautifulSoup
		import re

		soup = BeautifulSoup(body, features="lxml")
		images_with_cid = soup('img', attrs = {'src' : re.compile('cid:.*')})
		for image_tag in images_with_cid:
			image_tag['src'] = config["main"]["baseurl"]+'attach?rss_name='+self.rss_name+'&uid='+str(msgn)+'&cid='+image_tag['src'][4:]
			image_tag['style'] = "max-width: 100%; max-height: 100%;"
		return soup.renderContents().decode('utf-8')

	def getImage(self, msgn, cid):
		self.mailserver.select(self.mailbox)
		typ, data = self.mailserver.uid('fetch', msgn, '(RFC822)')

		try:
			mail = email.message_from_string(data[0][1])
		except:
			mail = email.message_from_bytes(data[0][1])

		try:
			attach, typ = self._getAttachment(mail, cid)
		except TypeError as e:
			app.logger.error("getImage(): "+str(e))
			abort(404)

		return attach, typ

	def getEMail(self, msgn):
		self.mailserver.select(self.mailbox)
		#print(f"Msgn: {msgn}")
		typ, data = self.mailserver.uid('fetch', msgn, '(RFC822)')
		#print(f"Typ: {typ}")
		#print(f"Data: {data}")
		try:
			mail = email.message_from_string(data[0][1])
		except:
			mail = email.message_from_bytes(data[0][1])

		from_name = self.decode_email(mail['From'],0)
		from_email = self.decode_email(mail['From'],1)
		subject = self.decode_email(mail['subject'])
		date = mail['Date']
		#print(f"From: {from_name}, {from_email}, subject: {subject}, at: {date}")

		if from_email is None:
			from_email = config['imap'][self.imapname].get("default-from","no-reply@my.domain")

		body, ctype = self._getBody(mail)
		if ctype == "text/html":
			body = self.cid_2_images(body, msgn)

		return {"subject": subject, "From": {'name': from_name, 'email': from_email}, "date": date, "body": body}

@app.route("/attach")
def AttachReader():
	rss_name = request.args.get('rss_name', 'None')
	uid = request.args.get('uid', 'None')
	cid = request.args.get('cid', 'None')
	app.logger.info("AttachReader " + uid + "	" + cid)
	if rss_name=='None' or uid=='None' or cid=='None':
		abort(404)
	client = EmailClient(rss_name)
	attach, typ = client.getImage(uid, cid)
	response = make_response(attach)
	response.headers['Content-Type'] = typ
	return response

@app.route("/mail")
def EmailReader():
	rss_name = request.args.get('rss_name', 'None')
	uid = request.args.get('uid', 'None')
	from bs4 import BeautifulSoup, Doctype
	app.logger.info("EmailReader " + rss_name + " " + uid)
	if rss_name=='None' or uid=='None':
		abort(404)
	client = EmailClient(rss_name)
	mail = client.getEMail(uid)
	subject = mail.get('subject','No subject...')
	if 'body' in mail:
		soup = BeautifulSoup(mail['body'], features="lxml")
	else:
		soup = BeautifulSoup(f'<html><body><h1>{subject}</h1></body></html>', features="lxml")
	if soup.find('head') == None:
		head = soup.new_tag("head")
		soup.html.insert(0, head)
	if soup.find('title') == None or soup.find('title') == "":
		title = soup.new_tag("title")
		soup.html.head.insert(0, title)
		soup.html.head.title.append(subject)
	for item in soup.contents:
		if isinstance(item, Doctype):
			item.extract()
	html = soup
	head = soup.html.head

	#subject = mail.get('subject','No subject...')
	#if 'body' in mail:
	#	soup = BeautifulSoup(mail['body'], features="lxml")
	#else:
	#	soup = BeautifulSoup(f'<html><body><h1>{subject}</h1></body></html>', features="lxml")
	#subject = NavigableString(subject)
	#title = Tag(soup, "title")
	#title.insert(0, subject)
	#
	#if soup.find('head') == None:
	#	head = Tag(soup, "head")
	#	html = Tag(soup, "html")
	#	html.insert(0, head)
	#	body = Tag(soup, "body")
	#	body.insert(0, soup)
	#	html.insert(0, body)
	#else:
	#	head = soup.html.head
	#	html = soup

	# Redirecting
	# We might want to lookup the content through a different URL
	if 'redirecturl' in config['main'] and 'redirectdomain' in config['main']:
		app.logger.info("Adding Redirects")
		meta = Tag(soup, "meta")
		meta['http-equiv'] = "refresh"
		meta['content'] = "0;url="+config['main']['redirecturl']+"?"+uid
		link = Tag(soup, "link")
		link['rel'] = "canonical"
		link['href'] = config['main']['redirecturl']+"?"+uid
		js = Tag(soup, "script")
		js['type'] = "text/javascript"
		script = NavigableString("if(document.domain != '"+config['main']['redirectdomain']+"') window.location.href ='" + config['main']['redirecturl']+"?"+uid+"'")
		js.insert(0, script)

		head.insert(0, title)
		head.insert(0, link)
		head.insert(0, js)

	response = make_response(html.renderContents().decode('utf-8'))
	response.headers["Access-Control-Allow-Origin"] = "*"
	return response

@app.route("/rss")
def RSSClient():
	rss_name = request.args.get('rss_name', 'None')
	if rss_name=='None':
		abort(404)
	fg = FeedGenerator()
	#TODO create icon
	# fg.icon('http://www.det.ua.pt')
	fg.title(config['rss'][rss_name]['title'])
	fg.description(config['rss'][rss_name]['description'])
	if 'language' in config['rss'][rss_name]:
		fg.language(config['rss'][rss_name]['language'])
	fg.link(href=config['rss'][rss_name]['href'], rel='related')
	client = EmailClient(rss_name)

	for msgn in reversed(client.listBox()[:config['rss'].get('maxitems', 10)]):
		app.logger.info("RSS Entry: "+msgn.decode('utf-8'))
		em = client.getEMail(msgn)
		entry = fg.add_entry()
		entry.title(em['subject'])
		entry.guid(config["main"]["baseurl"]+'mail?rss_name='+rss_name+'&uid='+msgn.decode('utf-8'))
		entry.link({'href':config["main"]["baseurl"]+'mail?rss_name='+rss_name+'&uid='+msgn.decode('utf-8'), 'rel':'alternate'})
		entry.pubDate(em['date'])
		entry.content(em['body'])
	response = make_response(fg.rss_str(pretty=True))
	response.headers["Access-Control-Allow-Origin"] = "*"
	response.headers['Content-Type'] = 'application/rss+xml'
	return response

config = toml.load("config.toml")

debug = config['main'].get('debug', False)
port = config['main'].get('port', 80)
host = config['main'].get('host', 'localhost')

app.run(host=host, port=port, debug=debug)
