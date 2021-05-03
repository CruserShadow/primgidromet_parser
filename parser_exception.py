class PrimGidroMet(Exception):
    pass


class VariableNotFoundError(PrimGidroMet):
    pass


class NotLoggedInError(PrimGidroMet):
    pass


class ParseError(PrimGidroMet):
    pass


class IncorrectPageError(PrimGidroMet):
    pass
