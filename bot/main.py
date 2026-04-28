import datetime
import re
import time
import logging
import os
import traceback

import praw

from .webhook import Webhook
from .config import Config

log = logging.getLogger(__name__)

class RedditBot:
    def __init__(self):
        # Make sure the data folder exists
        if not os.path.exists('data'):
            os.makedirs('data')

        log.info("Loading configuration...")
        self.config = Config()
        self.reddit = self.create_reddit_instance()

    def handle_new(self):
        """Monitors subreddits"""
        sub_names = []
        sub_colors = {}
        for h in self.config.hooks:
            for s in h.subreddits:
                if isinstance(s, str):
                    sub_names.append(s)
                elif isinstance(s, dict):
                    name = s.get("name")
                    sub_names.append(name)
                    if "color" in s:
                        sub_colors[name] = s["color"]
        if not sub_names:
            raise ValueError('There are no subreddits to monitor')

        subs = '+'.join(set(sub_names))
        sub = self.reddit.subreddit(subs)
        log.info("Monitoring subreddits: {}".format(subs))

        c_stream = sub.stream.comments(pause_after=0, skip_existing=True)
        s_stream = sub.stream.submissions(pause_after=0, skip_existing=True)

        while True:
            try:
                last_time = datetime.datetime.fromisoformat(self.grab_last_time('data/last_check.txt'))
            except Exception as e:
                last_time = None
            try:
                for c in c_stream:
                    if c is None:
                        break
                    if any(c.author and c.author.name and u.lower() == c.author.name.lower() for u in self.config.ignore_list):
                        break
                    for h in self.config.hooks:
                        rgx_match = re.findall(h.regex, c.body)
                        if (rgx_match and str(c.subreddit) in sub_names):
                            comment_time = datetime.datetime.fromtimestamp(c.created_utc, datetime.timezone.utc)
                            log.debug('Criteria was matched ({0}): {1}'.format(comment_time, rgx_match))
                            
                            diff_time = last_time-datetime.timedelta(minutes=10)
                            
                            if (last_time is None) or (comment_time > diff_time):
                                # Handle the comment
                                log.info("New comment: {0} ({0.subreddit.display_name})".format(c))
                                comment_color = None
                                if str(post.subreddit) in sub_colors:
                                    post_color = sub_colors.get(str(c.subreddit))
                                self.handle_comment(c, h, comment_color)
                            else:
                                log.debug('Skipping. Comment time was over 10 mins before last check ({0}).'.format(comment_time))

                for post in s_stream:
                    if post is None:
                        break
                    if any(post.author and post.author.name and u.lower() == post.author.name.lower() for u in self.config.ignore_list):
                        break
                    check = [post.url, post.title, post.selftext]

                    for h in self.config.hooks:
                        matching_rgx = [c for c in check if re.findall(h.regex, c)]

                        if (matching_rgx and str(post.subreddit) in sub_names):  # One or more criteria was matched
                            post_time = datetime.datetime.fromtimestamp(post.created_utc, datetime.timezone.utc)
                            log.debug('Criteria was matched ({0}): {1}'.format(post_time, matching_rgx))
                            
                            diff_time = last_time-datetime.timedelta(minutes=10)

                            if (last_time is None) or (post_time > diff_time):
                                log.info("New post: {0.title} ({0.subreddit.display_name})".format(post))
                                post_color = None
                                if str(post.subreddit) in sub_colors:
                                    post_color = sub_colors.get(str(post.subreddit))
                                self.handle_post(post, h, post_color)
                            else:
                                log.debug('Skipping. Post time was over 10 mins before last check ({0}).'.format(post_time))
            
                self.save_last_time('data/last_check.txt', datetime.datetime.now(datetime.timezone.utc))

            except Exception as e:
                if '503' in str(e):  # Reddit's servers are doing some weird shit
                    log.error("Received 503 from Reddit ({}). Waiting before restarting...".format(e))
                    time.sleep(30)  # Wait 30 seconds before trying again
                    log.warning("Restarting monitoring after 503...")
                else:
                    log.error("An error occurred: {0}\n".format(e, traceback.format_exc()))
                self.handle_new()  # Go again

    def handle_post(self, post, hook, color):
        """Handles an individual post"""
        if hook.url:
            self.handle_discord(post, hook.url, color)

    def handle_comment(self, comment, hook, color):
        """Handles an individual comment"""
        if hook.url:
            self.handle_discord(comment, hook.url, color)

    def handle_discord(self, data, url, color):
        """Handles the Discord webhooks"""
        embed = Webhook(url, color=color or 16729344)  # Default to a light red color if not specified

        if isinstance(data, praw.models.Submission):
            p_type = 'Submission'
            url = 'https://old.reddit.com' + data.permalink # data.shortlink
            title = data.title
            body = data.selftext if data.selftext and data.selftext.strip() else data.url
            thumb = self.config.sub_thumb
            if not data.is_self and data.thumbnail != 'default':
                thumb = data.thumbnail
            elif not data.is_self and data.thumbnail == 'default':
                if hasattr(data, 'preview') == True and 'images' in data.preview:
                    thumb = data.preview['images'][0]['source']['url']
        elif isinstance(data, praw.models.Comment):
            p_type = 'Comment'
            # Current Reddit interface only supports up to 3 levels of context.
            # More than 8 or so just doesn't load, 4-n will show context but not the actual linked comment.
            url = 'https://old.reddit.com' + data.permalink + '?context=1000'
            title = data.submission.title
            body = data.body
            thumb = self.config.comment_thumb
        else:
            log.warning('Received data that was not a submission or comment: {0}'.format(data))
            return

        author_name = 'none'
        if data.author and data.author.name:
            author_name = data.author.name
        
        embed.set_author(name='{0} on /r/{1}'.format(author_name, data.subreddit.display_name), icon=data.subreddit.icon_img, url='https://reddit.com/u/{0}'.format(author_name))
        embed.set_title(title=p_type, url=url)
        embed.add_field(name='**{0}**'.format(title), value=body[:750] + (body[750:] and '...'))
        embed.set_thumbnail(thumb)
        # embed.set_footer(text=self.config.footer_text, ts=True, icon=self.config.footer_icon)

        e = embed.post()
        return e

    def grab_last_time(self, path):
        """Reads timestamp from a file"""
        try:
            ts = None
            with open(path) as f:
                ts = str(f.read())
            return ts
        except FileNotFoundError:
            log.debug('Creating new file as it does not exist: {}'.format(path))
            open(path, 'a').close()  # Create the file
            return None
        except Exception as e:
            log.error("There was a problem reading the last submission cache file. ({})".format(e))
            return None
        return time

    def save_last_time(self, path, timestamp):
        """Saves timestamp to a file"""
        try:
            with open(path, 'w') as f:
                f.write(str(timestamp))
        except Exception as e:
            log.error("There was a problem writing to the last submission cache file. ({})".format(e))
        return True

    def create_reddit_instance(self):
        log.debug('Creating new praw.Reddit instance')
        return praw.Reddit(client_id=self.config.reddit_clientid,
                           client_secret=self.config.reddit_clientsecret,
                           user_agent=self.config.reddit_useragent,
                           username=self.config.reddit_username,
                           password=self.config.reddit_password)

if __name__ == '__main__':
    raise RuntimeError('This file cannot be executed directly.')
