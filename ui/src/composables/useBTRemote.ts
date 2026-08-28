import { useDeviceState } from '@/composables/useDeviceState';
import { useWebSocket } from '@/composables/useWebSocket';
import type { BTControlMsg } from '@/types/ws';

export function useBTRemote() {
  const { btDevices, btPlayer } = useDeviceState();
  const { send } = useWebSocket();

  function control(action: BTControlMsg['action'], address?: string) {
    const msg: BTControlMsg = { type: 'btControl', action };
    if (address !== undefined) {
      msg.address = address;
    }
    send(msg);
  }

  return {
    btDevices,
    btPlayer,
    scan: () => control('scan'),
    stopScan: () => control('stopScan'),
    pair: (address: string) => control('pair', address),
    connect: (address: string) => control('connect', address),
    disconnect: (address: string) => control('disconnect', address),
    forget: (address: string) => control('forget', address),
    playPause: () => control('playPause'),
    next: () => control('next'),
    previous: () => control('previous'),
  };
}
