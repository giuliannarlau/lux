let imagePreview = document.getElementById('imagePreview');
let cropper;
let outputImage = document.getElementById("imageCropped");
let base64Img= document.getElementById("base64Image");

/**
 * Shows a preview of the selected image and initializes the cropper tool.
 * Handles file size validation, displaying an error modal if the file is too large.
 * @param {HTMLInputElement} imageInput - The input element that contains the file.
 */
function showImagePreview(imageInput) {
    const file = imageInput.files[0];

    // Display an error if the file size exceeds the 900KB
    if (file.size > 900000) {
        document.getElementById("modalTitle").innerHTML = "Oops! The image size is too large";
        document.getElementById("modalBody").textContent = "Please choose an image that is 900KB or smaller.";
        const modal = new bootstrap.Modal(document.getElementById("alertModal"));
        modal.show();
    } else {

        // Destroy current cropper if exists
        if (cropper) {
            cropper.destroy();
        }

        // Set the image preview source
        imagePreview.src = URL.createObjectURL(file);
        imagePreview.onload = () => {
            URL.revokeObjectURL(imagePreview.src);
        }

        // Initialize the cropper on the preview
        cropper = new Cropper(imagePreview, {
            aspectRatio: 1,
            viewMode: 3,
        });
        
        // Read the file as Data URL to set base64 value
        const reader = new FileReader();
        reader.onloadend = function() {
            base64Img.value = reader.result;
        }
        reader.readAsDataURL(file);

        // Set and show the cropped image
        outputImage.src = URL.createObjectURL(file);
        outputImage.hidden = false;
        document.getElementById("croppedImgCol").hidden = false;
        document.getElementById("cropImageBtn").hidden = false;
        document.getElementById("cropImageBtn").disabled = false;
    }
}

// Crops the selected image and updates the UI with the cropped version
function cropImage() {

    // Get the cropped image data URL and lower quality
    let croppedImage = cropper.getCroppedCanvas().toDataURL("image/jpg", 0.2);

    // Update the source and input
    outputImage.src = croppedImage;
    base64Img.value = croppedImage;
}