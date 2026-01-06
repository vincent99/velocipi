export function strPad(str: string, toLength: number, padChars = ' ', right = false) {
  str = `${str}`;

  if (str.length >= toLength) {
    return str;
  }

  const neededLen = toLength - str.length + 1;
  const padStr = (new Array(neededLen)).join(padChars).substr(0, neededLen);

  if (right) {
    return str + padStr;
  } else {
    return padStr + str;
  }
}
