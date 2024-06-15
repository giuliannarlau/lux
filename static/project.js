/**
 * Checks if the given donation amount is a positive integer.
 * @param {number} amount - The donation amount to be validated.
 * @throws {Error} If the donation amount is not a positive integer.
 * @returns {boolean} True if the amount is valid, indicating the check has passed.
 */
function checkAmount(amount) {
    if (amount <= 0 || amount % 1 !== 0) {
        alert("The minimum donation amount is 1 lumen and must be an integer.");
        throw new Error("The amount must be a positive integer.");
    }
    return true;
};


/**
 * Builds the transaction envelope for a donation.
 * Sends the project ID and donation amount to the server via POST.
 * @returns {Promise<string>} A promise that resolves to the transaction envelope in XDR format.
 * @throws {Error} If there is a network or server error.
 */
async function buildDonationTransaction() {
    event.preventDefault();

    // Get project info and prepare to send it to the server
    const project_id = document.getElementById("projectId").value;
    const amount = document.getElementById("donationAmount").value;
    const body = {project_id: project_id, amount: amount};
    const requestOptions = {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(body)
    };

    try {
        let response = await fetch("/donate", requestOptions);
        let data = await response.json();

        // Return the transaction XDR
        return data.transaction_xdr;
    } catch (error) {
        console.error(error);
        throw error;
    }
};


/**
 * Processes a donation transaction.
 * Includes validation, creation, signing, and submission.
 */
async function processDonation() {
    
    try {
        // Check for valid donation amount and throws error if invalid
        checkAmount(Number(document.getElementById("donationAmount").value));

        // Build transaction envelope
        let transactionXdr = await buildDonationTransaction();

        // Sign transaction with Freighter extension
        let signedTransactionXdr = await signingTransaction(transactionXdr);

        // Update the modal to display a processing donation message
        let modalTitle = document.getElementById("modalTitle")
        let modalBody = document.getElementById("modalBody")
        modalTitle.innerHTML = "Processing your donation...";
        modalBody.textContent = "Please wait while we process your transaction.";
        
       // Block closing modal options
        setModalLockState("lock");

        // Send the signed transaction to Stellar and get hash response
        let hash = await sendTransaction(signedTransactionXdr);

        // Update the modal with confirmation and the transaction hash
        modalTitle.innerHTML = "Donation completed!";
        modalBody.textContent = "Here is your hash:" + hash + ". This transaction will be available on your account page.";

        // Allow user to close modal
        setModalLockState("unlock");

    } catch (error) {
        return console.log("Error: ", error);
    }
};