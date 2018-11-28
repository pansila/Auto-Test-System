*** Variables ***
${address_agent}            127.0.0.1
${port_agent}               8270
${port_test}                8271
${remote_agent_address}     http://${address_agent}:${port_agent}
${remote_test_address}      http://${address_agent}:${port_test}