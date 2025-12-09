import convict from 'convict'
import { ipaddress } from 'convict-format-with-validator'

convict.addFormat(ipaddress)

// Define a schema
var config = convict({
  env: {
    doc: 'The runtime environment.',
    format: ['production', 'development', 'test'],
    default: 'development',
    env: 'NODE_ENV'
  },
  ip: {
    doc: 'The IP address to bind.',
    format: 'ipaddress',
    default: '127.0.0.1',
    env: 'IP_ADDRESS',
  },
  port: {
    doc: 'The port to bind.',
    format: 'port',
    default: 8080,
    env: 'PORT',
    arg: 'port'
  },
  i2c: {
    device: {
      doc: 'The I2C device to use.',
      format: 'int',
      default: 1,
      env: 'I2C',
      arg: 'i2c'
    },
    expander: {
      doc: 'Expander board address',
      format: 'int',
      default: 0x20,
    }
  }
});

// Load environment dependent configuration
var env = config.get('env');
config.loadFile('./config/' + env + '.json');

// Perform validation
config.validate({allowed: 'strict'});

export default config
