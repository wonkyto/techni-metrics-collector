# techni-metrics-collector
This project collects metrics from a Telstra Technicolor gateway (DJA0231) including
* wan/lan interface metrics
* dls status, including line rates, SnR, power, attentuation.

This will only work on a gateway which has ssh enabled.

This has been developed to run on a raspberry pi, however there's no reason why this couldn't be built for x86.

## Docker
Development has been done using docker to facilitate a standard environment.
### Building the docker image
The docker image can be built in the following way:
```bash
make build
```
You'll want to build the image when you have finished development, or if you make any changes to the Dockerfile including python dependencies
### Testing the script
During development it is time consuming to build a new container, so you can simply mount the script into the existing container for testing. The python script can be tested in the following way:
```bash
make test
```
### Linting the script
During development you can run flake8 on the script:
```bash
make flake8
```

### Running the script
Once you have finished development, build the docker image, and run it using:
```bash
make run
```

## Configuration
The container requires both a configuration file to be present, and also an ssh username/password  which gives access to the root user on your gateway.

### config/config.yaml
Here we define the following:
 * InfluxDb: Your InfluxDB endpoint and db
 * Gateway: The ip/hostname and user credentials of your gateway switch
