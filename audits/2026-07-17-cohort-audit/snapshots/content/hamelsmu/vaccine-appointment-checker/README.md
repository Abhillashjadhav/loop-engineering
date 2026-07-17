# vaccine-appointment-checker

Apparently unused vaccines in the Portland, Oregon area are offered to the general public so they are not wasted.  

You have to keep refreshing [this page](https://mychartweb.ohsu.edu/mychart/SignupAndSchedule/EmbeddedSchedule?view=plain&public=1&id=84586,84587,84590&dept=237170004,237160001&vt=7504) to see if appointments are available.  Rather than do that, this repo contains a GitHub Action that checks the site every minute and sends a message if an appointment is available.


Edit: Since GitHub Actions can only run with a max frequency of every 5 minutes, I'm also running this in a CRON job code on my own server.  
