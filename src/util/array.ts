export function removeObject<T>(ary: T[], obj: T): T[] {
  const idx = ary.indexOf(obj);

  if ( idx >= 0 ) {
    ary.splice(idx, 1);
  }

  return ary;
}

export function removeObjects<T>(ary: T[], objs: T[]): T[] {
  let i;
  let indexes = [];

  for ( i = 0 ; i < objs.length ; i++ ) {
    let idx = ary.indexOf(objs[i]);

    // Find multiple copies of the same value
    while ( idx !== -1 ) {
      indexes.push(idx);
      idx = ary.indexOf(objs[i], idx + 1);
    }
  }

  if ( !indexes.length ) {
    // That was easy...
    return ary;
  }

  indexes = indexes.sort((a, b) => a - b);

  const ranges = [];
  let first: number;
  let last: number;

  // Group all the indexes into contiguous ranges
  while ( indexes.length ) {
    first = indexes.shift() as number;
    last = first;

    while ( indexes.length && indexes[0] === last + 1 ) {
      last = indexes.shift() as number;
    }

    ranges.push({ start: first, end: last });
  }

  // Remove the items by range
  for ( i = ranges.length - 1 ; i >= 0 ; i--) {
    const { start, end } = ranges[i];

    ary.splice(start, end - start + 1);
  }

  return ary;
}

export function addObject<T>(ary: T[], obj: T): void {
  const idx = ary.indexOf(obj);

  if ( idx === -1 ) {
    ary.push(obj);
  }
}

export function addObjects<T>(ary: T[], objs: T[]): void {
  const unique: T[] = [];

  for ( const obj of objs ) {
    if ( !ary.includes(obj) && !unique.includes(obj) ) {
      unique.push(obj);
    }
  }

  ary.push(...unique);
}

export function insertAt<T>(ary: T[], idx: number, ...objs: T[]): void {
  ary.splice(idx, 0, ...objs);
}

export function isArray<T>(thing: T[] | unknown): boolean {
  return Array.isArray(thing);
}

export function removeAt<T>(ary: T[], idx: number, length = 1): T[] {
  if ( idx < 0 ) {
    throw new Error('Index too low');
  }

  if ( idx + length > ary.length ) {
    throw new Error('Index + length too high');
  }

  ary.splice(idx, length);

  return ary;
}

export function clear<T>(ary: T[]): void {
  ary.splice(0, ary.length);
}

export function replaceWith<T>(ary: T[], ...values: T[]): void {
  ary.splice(0, ary.length, ...values);
}
