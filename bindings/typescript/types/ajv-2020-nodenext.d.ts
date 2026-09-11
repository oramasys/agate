// ajv publishes its draft-2020 build as CommonJS with ESM-flavored .d.ts; under
// moduleResolution NodeNext TypeScript resolves every import (default AND the
// root "ajv" class) to a module namespace with no construct signature (TS2351)
// even though the runtime default export used by tsx is the Ajv2020 class.
// ajv has no ESM/CJS dual types to fix this upstream, so this ambient module
// declaration provides minimal, honest constructable typing for the surface
// this binding uses (compile<T> + allErrors validation errors).
declare module "ajv/dist/2020.js" {
  export interface AjvOptions {
    allErrors?: boolean;
    strict?: boolean | "log";
  }

  export interface ErrorObject {
    instancePath: string;
    message?: string;
    [keyword: string]: unknown;
  }

  export interface ValidateFunction<T> {
    (data: unknown): data is T;
    errors: ErrorObject[] | null | undefined;
  }

  export class Ajv2020 {
    constructor(options?: AjvOptions);
    compile<T>(schema: object | boolean): ValidateFunction<T>;
  }

  export default Ajv2020;
}
