package wave

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/ecdsa"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"math/big"

	"tinygo.org/x/bluetooth"
)

const MANUFACTURER_KEY = 0xb5b5
const SERVICE_UUID = "00000001-0000-1000-8000-00805f9b34fb"
const WRITE_CHARACTERISTIC = "00000002-0000-1000-8000-00805f9b34fb"
const NOTIFY_CHARACTERISTIC = "00000003-0000-1000-8000-00805f9b34fb"

type Wave struct {
	adapter *bluetooth.Adapter
	device *bluetooth.Device
	address bluetooth.Address
	writeChar  *bluetooth.DeviceCharacteristic
	notifyChar *bluetooth.DeviceCharacteristic

	name string
	serial string

	privateKey *ecdsa.PrivateKey
	publicKey *ecdsa.PublicKey
	devPubKey *ecdsa.PublicKey
	sharedKey *ecdsa.PrivateKey
	iv []byte
}

func New() (*Wave, error) {
	wave := &Wave{
		adapter: bluetooth.DefaultAdapter,
	}

	err := wave.adapter.Enable()
	if err != nil {
		return nil, err
	}

	return wave, nil
}

func (w *Wave) Scan() error {
	println("Scanning...")

	err := w.adapter.Scan(func(adapter *bluetooth.Adapter, device bluetooth.ScanResult) {
		name := device.LocalName()
		data :=	device.ManufacturerData()
		if len(data) == 0 || data[0].CompanyID != MANUFACTURER_KEY || len(data[0].Data) < 17 {
			return
		}

		serial :=	string(data[0].Data[1:17])
		if serial[0:4] != "AC71" {
			return
		}

		w.name = name
		w.address = device.Address
		w.serial = serial
		fmt.Printf("Serial Number: %s\n", serial)
		w.adapter.StopScan()
		fmt.Printf("Found EcoFlow Wave %s (%s) at %s\n", name, serial, w.address.String())
	})

	return err
}

func (w *Wave) Connect() error {
	err := w.Scan()
	if err != nil {
		return fmt.Errorf("EcoFlow Wave not found")
	}

	device, err := w.adapter.Connect(w.address, bluetooth.ConnectionParams{})
	if err != nil {
		return err
	}

	w.device = &device

	svcUuid, _ := bluetooth.ParseUUID(SERVICE_UUID)
	writeUuid, _ := bluetooth.ParseUUID(WRITE_CHARACTERISTIC)
	notifyUuid, _ := bluetooth.ParseUUID(NOTIFY_CHARACTERISTIC)

	services, err := device.DiscoverServices([]bluetooth.UUID{svcUuid})
	fmt.Println("Discovered services:", services, err)

	chars, err := services[0].DiscoverCharacteristics([]bluetooth.UUID{writeUuid, notifyUuid})
	fmt.Println("Discovered characteristics:", chars, err)

	w.writeChar = &chars[0]
	w.notifyChar = &chars[1]

	return w.initSessionKey()
}

func (w *Wave) IsFound() bool {
	return w.address.String() != ""
}

func (w *Wave) IsConnected() bool {
	return false
}

func (w *Wave) initSessionKey() error {
	priv, err := ecdsa.GenerateKey(P160(), rand.Reader)
	if err != nil {
		return err
	}

	w.privateKey = priv
	w.publicKey = &priv.PublicKey

	key := append(w.publicKey.X.Bytes(), w.publicKey.Y.Bytes()...)
	payload := append([]byte{0x01, 0x00}, key...)
	packet := NewPacket(FRAME_TYPE_COMMAND, PAYLOAD_TYPE_VX_PROTOCOL, payload)

	bytes := packet.ToBytes()
	fmt.Printf("initSessionKey(%d): %s\n", len(bytes), hex.EncodeToString(bytes))

	return w.sendRequest(packet.ToBytes(), w.initSessionKeyHandler)
}

func (w *Wave) initSessionKeyHandler(raw []byte) {
	res, err := ParseSimple(raw)
	fmt.Printf("initSessionKeyHandler(%s): %s\n", err, hex.EncodeToString(res))

	typeSize := sizeForType(res[2])
	key := res[3 : 3+typeSize]

	w.devPubKey = &ecdsa.PublicKey{
		Curve: P160(),
		X:     new(big.Int).SetBytes(key[:typeSize/2]),
		Y:     new(big.Int).SetBytes(key[typeSize/2:]),
	
	}
	// devicePublicKey, err := ecdh.Curve.NewPublicKey(P160(), res[3 : 3+typeSize])
	
	// ecdsa.NewPublicKey(P160(), raw[3 : 3+typeSize])

	/*
	  ecdh_type_size = getEcdhTypeSize(data[2])
        self._dev_pub_key = ecdsa.VerifyingKey.from_string(data[3:ecdh_type_size+3], curve=ecdsa.SECP160r1)

        # Generating shared key from our private key and received device public key
        # NOTE: The device will do the same with it's private key and our public key to generate the
        # same shared key value and use it to encrypt/decrypt using symmetric encryption algorithm
        self._shared_key = ecdsa.ECDH(ecdsa.SECP160r1, self._private_key, self._dev_pub_key).generate_sharedsecret_bytes()
        # Set Initialization Vector from digest of the original shared key
        self._iv = hashlib.md5(self._shared_key).digest()
        if len(self._shared_key) > 16:
            # Using just 16 bytes of generated shared key
            self._shared_key = self._shared_key[0:16]

        await self.getKeyInfoReq()
	*/
}

func (w *Wave) sendRequest(payload []byte, handler func([]byte)) error {
	n, err := w.writeChar.Write(payload)

	if n != len(payload) {
		return fmt.Errorf("partial write: Wrote %d of %d bytes", n, len(payload))
	}

	// fmt.Printf("Wrote %d of %d bytes: %s\n", n, len(payload), hex.EncodeToString(payload))

	if err != nil {
		fmt.Printf("Write Error: %s\n", err)
		return err
	}

	w.notifyChar.EnableNotifications(func(response []byte) {
		// fmt.Printf("Recevied %d byte response: %s\n", len(response), hex.EncodeToString(response))
		handler(response)
		w.notifyChar.EnableNotifications(nil)
	})

	return nil
}

func (w *Wave) decryptShared(ciphertext []byte) ([]byte) {
	block, err := aes.NewCipher(w.sharedKey)
	if err != nil {
		panic(err)
	}

	plaintext := make([]byte, len(ciphertext))
	mode := cipher.NewCBCDecrypter(block, w.iv)
	mode.CryptBlocks(plaintext, ciphertext)

	return PKCS7UnPadding(plaintext)
}

func (w *Wave) decryptSession(ciphertext []byte) ([]byte) {
	block, err := aes.NewCipher(w.sessionKey)
	if err != nil {
		panic(err)
	}

	plaintext := make([]byte, len(ciphertext))
	mode := cipher.NewCBCDecrypter(block, w.iv)
	mode.CryptBlocks(plaintext, ciphertext)

	return PKCS7UnPadding(plaintext)
}

func sizeForType(t byte) int {
	if t == 1 {
		return 52
	} else if t == 2 {
		return 56
	} else if t == 3 || t == 4 {
		return 64
	} else {
		return 40
	}
}


// essionKey(self):
//         print("%s: initBleSessionKey: Pub key exchange" % (self._address,))
//         self._private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP160r1)
//         self._public_key = self._private_key.get_verifying_key()

//         to_send = EncPacket(
//             EncPacket.FRAME_TYPE_COMMAND, EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
//             # Payload contains some weird prefix and generated public key
//             b'\x01\x00' + self._public_key.to_string(),
//         ).toBytes()

//         # Device public key is sent as response, process will continue on device response in handler
//         await self.sendRequest(to_send, self.initBleSessionKeyHandler)

//     async def initBleSessionKeyHandler(self, characteristic: BleakGATTCharacteristic, recv_data: bytearray):
//         await self._client.stop_notify(Connection.NOTIFY_CHARACTERISTIC)

//         data = await self.parseSimple(bytes(recv_data))
//         status = data[1]
//         ecdh_type_size = getEcdhTypeSize(data[2])
//         self._dev_pub_key = ecdsa.VerifyingKey.from_string(data[3:ecdh_type_size+3], curve=ecdsa.SECP160r1)

//         # Generating shared key from our private key and received device public key
//         # NOTE: The device will do the same with it's private key and our public key to generate the
//         # same shared key value and use it to encrypt/decrypt using symmetric encryption algorithm
//         self._shared_key = ecdsa.ECDH(ecdsa.SECP160r1, self._private_key, self._dev_pub_key).generate_sharedsecret_bytes()
//         # Set Initialization Vector from digest of the original shared key
//         self._iv = hashlib.md5(self._shared_key).digest()
//         if len(self._shared_key) > 16:
//             # Using just 16 bytes of generated shared key
//             self._shared_key = self._shared_key[0:16]

//         await self.getKeyInfoReq()

//     async def getKeyInfoReq(self):
//         print("%s: INFO: getKeyInfoReq: Receiving session key" % (self._address,))
//         to_send = EncPacket(
//             EncPacket.FRAME_TYPE_COMMAND, EncPacket.PAYLOAD_TYPE_VX_PROTOCOL,
//             b'\x02',  # command to get key info to make the shared key
//         ).toBytes()

//         await self.sendRequest(to_send, self.getKeyInfoReqHandler)

//     async def getKeyInfoReqHandler(self, characteristic: BleakGATTCharacteristic, recv_data: bytearray):
//         print("1")
//         await self._client.stop_notify(Connection.NOTIFY_CHARACTERISTIC)
//         print("2")
//         encrypted_data = await self.parseSimple(bytes(recv_data))
//         print("3", encrypted_data)

//         if encrypted_data[0] != 0x02:
//             raise Exception("Received type of KeyInfo is != 0x02, need to dig into: " + encrypted_data.hex())

//         # Skipping the first byte - type of the payload (0x02)
//         data = await self.decryptShared(encrypted_data[1:])
//         print("4", data)

//         # Parse the data that contains sRand (first 16 bytes) & seed (last 2 bytes)
//         self._session_key = await self.genSessionKey(data[16:18], data[:16])
//         print("5", self._session_key)

//         await self.getAuthStatus()
//         print("6")
