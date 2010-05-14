"""
Copyright 2009-2010 John B. Nelson <http://pathdependent.com/about/>

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at:

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
---
This project was originally named SMimimcS. I renamed it FakeSMS but 
didn't feel like setting up a new AppSpot project, hence the remaining
references to SMimicS.
"""

import os
import random
import datetime

from google.appengine.api import mail
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class SmimicsKey(db.Model):
    """Implements a key and counter for sending email to each user."""

    owner = db.UserProperty()
    validation_key = db.StringProperty()
    counter_last_reset_at = db.DateTimeProperty(auto_now_add=True)
    messages_since_reset = db.IntegerProperty(default=0)

    def sending_allowed(self):
        """Makes sure the user has not sent more than 100 messages a day.
        
        This is a cheap DoS attack prevention method given free app quotas.
        """
        time_since_reset = datetime.datetime.now() - \
            self.counter_last_reset_at
          

        if self.messages_since_reset > 100:
            if time_since_reset.seconds < 60*60*24:
                return False
            else:
                self.messages_since_reset = 0
                self.counter_last_reset_at = datetime.datetime.now()
                self.put()
        else:
            self.messages_since_reset += 1
            self.put()

        return True
    

def make_fakesms_url(email_address, key):
    return "http://fakesms.pathdependent.com/sms?e=%s&k=%s&s=your+message" % \
        (email_address, key)

class MainPage(webapp.RequestHandler):
    def get(self):
        template_values = {'deleted':self.request.get('deleted')}

        user = users.get_current_user()
        template_values['user'] = user

        if user:
            query = db.GqlQuery("SELECT * FROM SmimicsKey WHERE owner = :1", user)
            smimics_key = query.get()

            template_values['url'] = users.create_logout_url(self.request.uri)
            template_values['smimics_url'] = \
                make_fakesms_url(user.email(),smimics_key.validation_key)
            template_values['logout_url'] = \
                users.create_logout_url('/')
        else:
            template_values['url'] = users.create_login_url(self.request.uri)
            template_values['smimics_url'] = \
                make_fakesms_url('you@your.tld', 'YourKey')

        path = os.path.join(os.path.dirname(__file__), 'index.html')
        self.response.out.write(template.render(path, template_values))
        

class GetKey(webapp.RequestHandler):
    def get(self):
        """Generates a key if required."""
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        query = db.GqlQuery("SELECT * FROM SmimicsKey WHERE owner = :1", user)
        smimics_key = query.get()

        generation_required = True

        if smimics_key and self.request.get('skip_generation'):
            generation_required = False

        if generation_required:
            if not smimics_key:
                smimics_key = SmimicsKey()
            smimics_key.owner = user
            smimics_key.validation_key = \
                ''.join(random.sample('1234567890ABCFDEFabcdef', 10))
            smimics_key.put()
            
        self.redirect('/')

body_string = 'This Message was sent through http://fakesms.pathdependent.com/'
class SMS(webapp.RequestHandler):
    def get(self):
        recipient = db.GqlQuery(
            "SELECT * FROM SmimicsKey WHERE owner = USER(:1)",
            self.request.get('e')).get()

        subject = self.request.get('s')

        # Common practice is to limit a subject to 78 characters.
        if len(subject) > 78: 
            subject = subject[:78]

        if recipient and recipient.sending_allowed() and len(subject)>0 and \
                recipient.validation_key == self.request.get('k'):
            mail.send_mail(sender="fakesms@pathdependent.com",
                to=self.request.get('e'),
                subject=self.request.get('s'),
                body=body_string)
            self.response.out.write('True')
        else:
            self.response.out.write('False')

class DeleteAccount(webapp.RequestHandler):
    def post(self):
        user = users.get_current_user()
        if not user:
            self.redirect('/')
            return
        
        query = db.GqlQuery("SELECT * FROM SmimicsKey WHERE owner = :1", user)
        smimics_key = query.get()
        if smimics_key:
            smimics_key.delete()
        self.redirect(users.create_logout_url('/?deleted=True'))

application = webapp.WSGIApplication([ 
        ('/', MainPage), 
        ('/get_key', GetKey),
        ('/sms', SMS),  
        ('/delete_my_account', DeleteAccount)])

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
