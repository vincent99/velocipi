declare module 'rpi-io' {
  interface Options {
    value: number,
    bias: "disable"|"pull-up"|"pull-down",
    exportTime: number
    period: number
    dutyMin: number
    dutyMax: number
  }

  type MonitoringCallback = (edge: "rising"|"falling") => {};

  declare class RIO {
    constructor(line: number, mode: "input"|"output"|"pwm", opt: Partial<Options>);
    close(): void;
    write(value: number): void;
    read(): number;
    monitoringStart(cb: MonitoringCallback, edge: "rising"|"falling"|"both", bounce: number): void;
    monitoringStop(): void;
    pwmStop(): void;
    pwmDUty(percent: number): void;
    closeAll(): void;
  }
