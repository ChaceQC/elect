import { http, HttpResponse } from 'msw'
import scenarios from './scenarios.json'

/** @param {keyof typeof scenarios} scenario */
export function handlersFor(scenario) {
  return scenarios[scenario].map(({ method, path, status, body }) =>
    http.all(`/api/v1${path.replaceAll('{id}', ':id')}`, ({ request }) => {
      if (request.method.toLowerCase() !== method) return undefined
      return HttpResponse.json(body, { status })
    }),
  )
}
