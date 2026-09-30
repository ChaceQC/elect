/** @typedef {{bindingId?: string|null, start?: string, end?: string, granularity?: string,
 * page?: number, pageSize?: number, snapshot?: string|null}} QueryScope */

/** @param {string} resource @param {string} userId @param {QueryScope} [scope] */
export const resourceKey = (resource, userId, scope = {}) => [resource, userId, scope]

/** @param {string} userId @param {'operation'|'run'|'order'} kind @param {string|null} id */
export const operationKey = (userId, kind, id) => [kind, userId, id]
