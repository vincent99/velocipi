import { Expander } from "./expander";

export type Type = 'button' | 'rotary'

export interface Definition {
  bit: number,
  length: number,
  name: string,
  letter: string,
  type: Type
}

export class Buttons {
  private expander: Expander;
  private defs: Definition[]

  constructor(expander: Expander, defs: Definition[]) {
    this.expander = expander
    this.defs = defs
  }
}
