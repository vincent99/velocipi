export function millitime(then?: number) {
  const hr = process.hrtime()
  const now = hr[ 0 ] * 1000 + hr[ 1 ] / 1000000;

  if (then) {
    return Math.round((now - then) * 1000) / 1000
  } else {
    return now
  }
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve, _) => {
    setTimeout(resolve, ms)
  })
}
