# Google API Acquisition Tool

Access many APIs and acquire as much user identifying information as possible.

## Getting Started

Only has been tested in a Linux environment.

Install python 3 / pip3

Install google api python client
pip3 install --upgrade google-api-python-client


### Prerequisites


### Installing


### Bugs or Issues

If you receive this error:
```
Failed to start a local webserver listening on either port 8080
or port 8090. Please check your firewall settings and locally
running programs that may be blocking or using those ports.
```

use: lsof -w -n -i tcp:8080 or lsof -w -n -i tcp:8090 respectively.
then: kill -9 PID

Or you can click the click provided in the terminal and then copy and paste
the key from the webpage that is launched.

## Authors

* **Daniel Caruso II** - *Creator* - [Daniel Caruso II](http://10.90.3.18/dmcaruso)
